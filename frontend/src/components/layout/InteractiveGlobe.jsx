import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import dayUrl from '../../assets/globe/earth-day.jpg'
import nightUrl from '../../assets/globe/earth-night.jpg'
import waterUrl from '../../assets/globe/earth-water.png'

/*
  Interactive 3D globe for the auth screens.

  - Drag to spin (with momentum), pinch or scroll to zoom, double-tap to zoom
    toward a spot, tap a city to see its local time. Arrow keys and +/- work
    when the globe is focused.
  - The day/night line follows the real time, so the side of the Earth that is
    dark on screen is dark outside too.
  - Sealed-message "comets" travel between the selected city and others.
  - Everything is rendered locally (textures are bundled), so the app's
    Content-Security-Policy does not need to change.
*/

const DEG = Math.PI / 180
const SIGNAL = '#49D6AC'

const MIN_DIST = 1.55
const MAX_DIST = 7
const DEFAULT_DIST = 4.0
const HOME_VIEW = { lat: 9, lon: 33 }

const CITIES = [
  { name: 'Nairobi', country: 'Kenya', lat: -1.286, lon: 36.817, tz: 'Africa/Nairobi' },
  { name: 'Mombasa', country: 'Kenya', lat: -4.043, lon: 39.668, tz: 'Africa/Nairobi' },
  { name: 'Kampala', country: 'Uganda', lat: 0.347, lon: 32.582, tz: 'Africa/Kampala' },
  { name: 'Dar es Salaam', country: 'Tanzania', lat: -6.792, lon: 39.208, tz: 'Africa/Dar_es_Salaam' },
  { name: 'Addis Ababa', country: 'Ethiopia', lat: 9.03, lon: 38.74, tz: 'Africa/Addis_Ababa' },
  { name: 'Lagos', country: 'Nigeria', lat: 6.524, lon: 3.379, tz: 'Africa/Lagos' },
  { name: 'Accra', country: 'Ghana', lat: 5.603, lon: -0.187, tz: 'Africa/Accra' },
  { name: 'Cairo', country: 'Egypt', lat: 30.044, lon: 31.236, tz: 'Africa/Cairo' },
  { name: 'Casablanca', country: 'Morocco', lat: 33.573, lon: -7.589, tz: 'Africa/Casablanca' },
  { name: 'Johannesburg', country: 'South Africa', lat: -26.204, lon: 28.047, tz: 'Africa/Johannesburg' },
  { name: 'Cape Town', country: 'South Africa', lat: -33.925, lon: 18.424, tz: 'Africa/Johannesburg' },
  { name: 'London', country: 'United Kingdom', lat: 51.507, lon: -0.128, tz: 'Europe/London' },
  { name: 'Paris', country: 'France', lat: 48.857, lon: 2.352, tz: 'Europe/Paris' },
  { name: 'Berlin', country: 'Germany', lat: 52.52, lon: 13.405, tz: 'Europe/Berlin' },
  { name: 'Dubai', country: 'United Arab Emirates', lat: 25.205, lon: 55.271, tz: 'Asia/Dubai' },
  { name: 'Mumbai', country: 'India', lat: 19.076, lon: 72.878, tz: 'Asia/Kolkata' },
  { name: 'Singapore', country: 'Singapore', lat: 1.352, lon: 103.82, tz: 'Asia/Singapore' },
  { name: 'Tokyo', country: 'Japan', lat: 35.676, lon: 139.65, tz: 'Asia/Tokyo' },
  { name: 'Sydney', country: 'Australia', lat: -33.869, lon: 151.209, tz: 'Australia/Sydney' },
  { name: 'New York', country: 'United States', lat: 40.713, lon: -74.006, tz: 'America/New_York' },
  { name: 'Toronto', country: 'Canada', lat: 43.653, lon: -79.383, tz: 'America/Toronto' },
  { name: 'San Francisco', country: 'United States', lat: 37.775, lon: -122.419, tz: 'America/Los_Angeles' },
  { name: 'Mexico City', country: 'Mexico', lat: 19.433, lon: -99.133, tz: 'America/Mexico_City' },
  { name: 'São Paulo', country: 'Brazil', lat: -23.55, lon: -46.633, tz: 'America/Sao_Paulo' },
]

/* ----------------------------- math helpers ----------------------------- */

// Matches the UV layout of THREE.SphereGeometry with an equirectangular map.
function latLonToVec3(lat, lon, r = 1, out = new THREE.Vector3()) {
  const phi = (90 - lat) * DEG
  const theta = (lon + 180) * DEG
  return out.set(-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta))
}

function vec3ToLatLon(v) {
  const n = v.clone().normalize()
  const lat = Math.asin(THREE.MathUtils.clamp(n.y, -1, 1)) / DEG
  const lon = Math.atan2(n.z, -n.x) / DEG - 180
  return { lat, lon: ((lon + 540) % 360) - 180 }
}

// Where the sun is directly overhead right now (good to ~1 degree).
function sunDirection(date = new Date()) {
  const dayOfYear = (date - Date.UTC(date.getUTCFullYear(), 0, 0)) / 864e5
  const declination = -23.44 * Math.cos(((2 * Math.PI) / 365) * (dayOfYear + 10))
  const hours = date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600
  return latLonToVec3(declination, -15 * (hours - 12)).normalize()
}

function arcPoints(a, b, segments = 72) {
  const angle = a.angleTo(b)
  const lift = 0.025 + 0.13 * (angle / Math.PI)
  const pts = []
  const ts = []
  const sinAngle = Math.sin(angle) || 1
  for (let i = 0; i <= segments; i++) {
    const t = i / segments
    const w1 = Math.sin((1 - t) * angle) / sinAngle
    const w2 = Math.sin(t * angle) / sinAngle
    const p = a.clone().multiplyScalar(w1).add(b.clone().multiplyScalar(w2)).normalize()
    p.multiplyScalar(1.004 + Math.sin(Math.PI * t) * lift)
    pts.push(p.x, p.y, p.z)
    ts.push(t)
  }
  return { positions: new Float32Array(pts), progress: new Float32Array(ts) }
}

function localTime(tz) {
  try {
    return new Intl.DateTimeFormat([], { hour: 'numeric', minute: '2-digit', timeZone: tz }).format(new Date())
  } catch {
    return ''
  }
}

/* -------------------------------- shaders ------------------------------- */

const EARTH_VERT = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vPos;
  void main() {
    vUv = uv;
    vPos = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const EARTH_FRAG = /* glsl */ `
  uniform sampler2D uDay;
  uniform sampler2D uNight;
  uniform sampler2D uWater;
  uniform vec3 uSun;
  uniform vec3 uCam;
  uniform vec3 uRim;
  varying vec2 vUv;
  varying vec3 vPos;

  void main() {
    vec3 N = normalize(vPos);
    vec3 V = normalize(uCam - vPos);
    vec3 L = normalize(uSun);
    float ndl = dot(N, L);
    float day = smoothstep(-0.14, 0.2, ndl);

    vec3 dayTex = texture2D(uDay, vUv).rgb;
    vec3 nightTex = texture2D(uNight, vUv).rgb;
    float water = texture2D(uWater, vUv).r;

    // Day side: wrap-lit, slightly deepened so it sits well on the dark UI.
    float lit = 0.5 + 0.62 * clamp(ndl, 0.0, 1.0);
    vec3 dayCol = pow(dayTex, vec3(1.06)) * lit * 1.12;

    // Night side: a faint landmass silhouette plus warm city lights.
    float lum = dot(nightTex, vec3(0.3, 0.59, 0.11));
    float lights = smoothstep(0.035, 0.32, lum);
    vec3 nightCol = nightTex * 1.5 + vec3(1.0, 0.7, 0.36) * lights * 2.1;

    vec3 col = mix(nightCol, dayCol, day);

    // Sun glint on the oceans.
    vec3 R = reflect(-L, N);
    float spec = pow(max(dot(R, V), 0.0), 46.0) * water * day;
    col += vec3(0.75, 0.9, 1.0) * spec * 0.55;

    // Twilight warmth along the terminator.
    float twilight = exp(-pow(ndl * 6.5, 2.0));
    col += vec3(0.95, 0.42, 0.22) * twilight * 0.018;

    // Atmospheric rim light, stronger on the sunlit side.
    float fres = pow(1.0 - max(dot(N, V), 0.0), 3.0);
    col += uRim * fres * (0.22 + 0.55 * day);

    gl_FragColor = vec4(col, 1.0);
    #include <colorspace_fragment>
  }
`

const ATMO_VERT = /* glsl */ `
  varying vec3 vN;
  varying vec3 vP;
  varying vec3 vW;
  void main() {
    vN = normalize(normalMatrix * normal);
    vW = normalize(position);
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vP = mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`

const ATMO_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uSun;
  varying vec3 vN;
  varying vec3 vP;
  varying vec3 vW;
  void main() {
    float d = dot(normalize(vN), normalize(-vP));
    float a = pow(clamp(-d * 1.75, 0.0, 1.0), 2.6);
    float sunSide = smoothstep(-0.55, 0.45, dot(vW, normalize(uSun)));
    gl_FragColor = vec4(uColor, a * mix(0.28, 0.95, sunSide));
    #include <colorspace_fragment>
  }
`

const ARC_VERT = /* glsl */ `
  attribute float aT;
  varying float vT;
  void main() {
    vT = aT;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const ARC_FRAG = /* glsl */ `
  uniform float uTime;
  uniform float uGrow;
  uniform float uOffset;
  uniform float uSpeed;
  uniform vec3 uColor;
  varying float vT;
  void main() {
    if (vT > uGrow) discard;
    float head = fract(uTime * uSpeed + uOffset);
    float d = head - vT;
    d = d < 0.0 ? d + 1.0 : d;
    float comet = exp(-d * 9.0);
    float base = 0.13 * sin(3.14159 * vT);
    gl_FragColor = vec4(uColor, base + 0.95 * comet);
    #include <colorspace_fragment>
  }
`

/* ------------------------------- component ------------------------------ */

export default function InteractiveGlobe({ paused = false, onUnsupported }) {
  const wrapRef = useRef(null)
  const chipRef = useRef(null)
  const apiRef = useRef(null)
  const [ready, setReady] = useState(false)
  const [interacted, setInteracted] = useState(false)
  const [selected, setSelected] = useState(0)
  const [, setClock] = useState(0)

  // Keep the local-time label fresh.
  useEffect(() => {
    const id = setInterval(() => setClock((n) => n + 1), 30000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const wrap = wrapRef.current
    if (!wrap) return undefined

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    /* ----- renderer ----- */
    let renderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    } catch {
      onUnsupported?.()
      return undefined
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setClearColor(0x000000, 0)
    const canvas = renderer.domElement
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block;touch-action:none;cursor:grab;outline:none'
    wrap.insertBefore(canvas, wrap.firstChild)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(35, 1, 0.05, 50)

    /* ----- textures ----- */
    const manager = new THREE.LoadingManager()
    const loader = new THREE.TextureLoader(manager)
    const maxAniso = Math.min(8, renderer.capabilities.getMaxAnisotropy())
    const load = (url, srgb) => {
      const t = loader.load(url)
      t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace
      t.anisotropy = maxAniso
      return t
    }
    const dayTex = load(dayUrl, true)
    const nightTex = load(nightUrl, true)
    const waterTex = load(waterUrl, false)

    /* ----- earth ----- */
    const sun = sunDirection()
    const earthMat = new THREE.ShaderMaterial({
      vertexShader: EARTH_VERT,
      fragmentShader: EARTH_FRAG,
      uniforms: {
        uDay: { value: dayTex },
        uNight: { value: nightTex },
        uWater: { value: waterTex },
        uSun: { value: sun },
        uCam: { value: new THREE.Vector3() },
        uRim: { value: new THREE.Color('#58c7d8') },
      },
    })
    const earthGeo = new THREE.SphereGeometry(1, 128, 96)
    const earth = new THREE.Mesh(earthGeo, earthMat)
    scene.add(earth)

    /* ----- atmosphere ----- */
    const atmoMat = new THREE.ShaderMaterial({
      vertexShader: ATMO_VERT,
      fragmentShader: ATMO_FRAG,
      uniforms: { uColor: { value: new THREE.Color('#4fc4d6') }, uSun: { value: sun } },
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false,
    })
    const atmoGeo = new THREE.SphereGeometry(1.17, 96, 64)
    scene.add(new THREE.Mesh(atmoGeo, atmoMat))

    /* ----- city pins ----- */
    const pinDotGeo = new THREE.SphereGeometry(0.0165, 16, 12)
    const pinRingGeo = new THREE.RingGeometry(0.02, 0.0245, 40)
    const pins = CITIES.map((city, i) => {
      const normal = latLonToVec3(city.lat, city.lon)
      const group = new THREE.Group()
      group.position.copy(normal).multiplyScalar(1.003)
      group.lookAt(normal.clone().multiplyScalar(2))
      const dotMat = new THREE.MeshBasicMaterial({ color: SIGNAL })
      const ringMat = new THREE.MeshBasicMaterial({
        color: SIGNAL,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
      const dot = new THREE.Mesh(pinDotGeo, dotMat)
      dot.scale.z = 0.5
      const ring = new THREE.Mesh(pinRingGeo, ringMat)
      group.add(dot, ring)
      scene.add(group)
      return { city, normal, group, dot, dotMat, ring, ringMat, phase: (i * 0.37) % 1 }
    })

    /* ----- arcs ----- */
    const arcGroup = new THREE.Group()
    scene.add(arcGroup)
    const arcColor = new THREE.Color('#8cf2d4')
    let arcs = []
    let arcsBornAt = 0
    const clearArcs = () => {
      arcs.forEach((a) => {
        arcGroup.remove(a.line)
        a.line.geometry.dispose()
        a.line.material.dispose()
      })
      arcs = []
    }
    const buildArcs = (index, now) => {
      clearArcs()
      const origin = pins[index]
      const ranked = pins
        .map((p, i) => ({ i, d: p.normal.angleTo(origin.normal) }))
        .filter((p) => p.i !== index)
        .sort((a, b) => a.d - b.d)
      const picks = [1, 3, 6, 9, 13, 18].map((k) => ranked[k % ranked.length])
      picks.forEach((pick, n) => {
        const { positions, progress } = arcPoints(origin.normal, pins[pick.i].normal)
        const geo = new THREE.BufferGeometry()
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
        geo.setAttribute('aT', new THREE.BufferAttribute(progress, 1))
        const mat = new THREE.ShaderMaterial({
          vertexShader: ARC_VERT,
          fragmentShader: ARC_FRAG,
          uniforms: {
            uTime: { value: 0 },
            uGrow: { value: reduceMotion ? 1 : 0 },
            uOffset: { value: (n * 0.17) % 1 },
            uSpeed: { value: 0.16 + (n % 3) * 0.03 },
            uColor: { value: arcColor },
          },
          transparent: true,
          depthWrite: false,
        })
        const line = new THREE.Line(geo, mat)
        arcGroup.add(line)
        arcs.push({ line, mat })
      })
      arcsBornAt = now
    }

    /* ----- camera state ----- */
    const cur = { lat: 18, lon: HOME_VIEW.lon - 70, dist: 8.5 }
    const tgt = { lat: HOME_VIEW.lat, lon: HOME_VIEW.lon, dist: DEFAULT_DIST }
    if (reduceMotion) Object.assign(cur, tgt)
    const vel = { lon: 0, lat: 0 }
    let introUntil = 0
    let lastInteract = 0
    let selectedIdx = 0
    let w = 1
    let h = 1

    const markInteraction = () => {
      lastInteract = performance.now()
      setInteracted(true)
    }

    const globeRadiusPx = () => {
      const half = h / 2
      const f = half / Math.tan((camera.fov * DEG) / 2)
      return (f / Math.sqrt(Math.max(cur.dist * cur.dist - 1, 0.05))) * 1
    }

    const resize = () => {
      const rect = wrap.getBoundingClientRect()
      w = Math.max(1, rect.width)
      h = Math.max(1, rect.height)
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      // Keep the whole globe in view on tall, narrow containers.
      const base = Math.tan((35 * DEG) / 2)
      camera.fov = (2 * Math.atan(base / Math.min(1, camera.aspect))) / DEG
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(wrap)
    resize()

    /* ----- selection ----- */
    const flyTo = (lat, lon) => {
      const dl = ((lon - cur.lon + 540) % 360) - 180
      tgt.lon = cur.lon + dl
      tgt.lat = THREE.MathUtils.clamp(lat, -80, 80)
      vel.lon = 0
      vel.lat = 0
    }
    const select = (i, now = performance.now(), zoom = false) => {
      selectedIdx = i
      setSelected(i)
      if (i >= 0) {
        buildArcs(i, now)
        flyTo(pins[i].city.lat, pins[i].city.lon)
        if (zoom) tgt.dist = Math.min(tgt.dist, 3.3)
      }
    }

    /* ----- hit testing ----- */
    const tmp = new THREE.Vector3()
    const camDir = new THREE.Vector3()
    const projectPin = (pin, out) => {
      tmp.copy(pin.group.position).project(camera)
      out.x = ((tmp.x + 1) / 2) * w
      out.y = ((1 - tmp.y) / 2) * h
      camDir.copy(camera.position).normalize()
      out.facing = pin.normal.dot(camDir) - 1 / cur.dist
    }
    const hitPin = (px, py) => {
      const o = { x: 0, y: 0, facing: 0 }
      let best = -1
      let bestD = 22
      pins.forEach((pin, i) => {
        projectPin(pin, o)
        if (o.facing < 0.02) return
        const d = Math.hypot(o.x - px, o.y - py)
        if (d < bestD) {
          bestD = d
          best = i
        }
      })
      return best
    }
    const raycaster = new THREE.Raycaster()
    const surfacePoint = (px, py) => {
      raycaster.setFromCamera(new THREE.Vector2((px / w) * 2 - 1, -(py / h) * 2 + 1), camera)
      const hit = raycaster.intersectObject(earth, false)[0]
      return hit ? vec3ToLatLon(hit.point) : null
    }

    /* ----- pointer input ----- */
    const pointers = new Map()
    let drag = null
    let pinch = null
    let lastTap = { t: 0, x: 0, y: 0 }

    const local = (e) => {
      const r = canvas.getBoundingClientRect()
      return { x: e.clientX - r.left, y: e.clientY - r.top }
    }

    const onDown = (e) => {
      canvas.setPointerCapture(e.pointerId)
      pointers.set(e.pointerId, local(e))
      markInteraction()
      if (pointers.size === 1) {
        const p = local(e)
        drag = { sx: p.x, sy: p.y, lx: p.x, ly: p.y, st: performance.now(), lt: performance.now(), moved: false }
        vel.lon = 0
        vel.lat = 0
        canvas.style.cursor = 'grabbing'
      } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()]
        pinch = { span: Math.hypot(a.x - b.x, a.y - b.y) || 1, dist: tgt.dist }
        drag = null
      }
    }

    const onMove = (e) => {
      const p = local(e)
      if (!pointers.has(e.pointerId)) {
        // Hover: show a pointer cursor over cities.
        if (e.pointerType === 'mouse') canvas.style.cursor = hitPin(p.x, p.y) >= 0 ? 'pointer' : 'grab'
        return
      }
      pointers.set(e.pointerId, p)
      markInteraction()
      if (pointers.size === 2 && pinch) {
        const [a, b] = [...pointers.values()]
        const span = Math.hypot(a.x - b.x, a.y - b.y) || 1
        tgt.dist = THREE.MathUtils.clamp(pinch.dist * (pinch.span / span), MIN_DIST, MAX_DIST)
        return
      }
      if (!drag) return
      const now = performance.now()
      const dx = p.x - drag.lx
      const dy = p.y - drag.ly
      if (Math.hypot(p.x - drag.sx, p.y - drag.sy) > 6) drag.moved = true
      const R = globeRadiusPx()
      const dLon = (-dx / (R * Math.max(Math.cos(cur.lat * DEG), 0.25))) / DEG
      const dLat = dy / R / DEG
      tgt.lon += dLon
      tgt.lat = THREE.MathUtils.clamp(tgt.lat + dLat, -82, 82)
      const dt = Math.max((now - drag.lt) / 1000, 0.008)
      vel.lon = vel.lon * 0.6 + (dLon / dt) * 0.4
      vel.lat = vel.lat * 0.6 + (dLat / dt) * 0.4
      drag.lx = p.x
      drag.ly = p.y
      drag.lt = now
    }

    const onUp = (e) => {
      const p = local(e)
      pointers.delete(e.pointerId)
      if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId)
      canvas.style.cursor = 'grab'
      if (pointers.size < 2) pinch = null
      if (!drag) return
      const now = performance.now()
      const wasTap = !drag.moved && now - drag.st < 450
      const stale = now - drag.lt > 90
      drag = null
      if (stale) {
        vel.lon = 0
        vel.lat = 0
      }
      if (!wasTap) return
      vel.lon = 0
      vel.lat = 0

      const isDouble = now - lastTap.t < 320 && Math.hypot(p.x - lastTap.x, p.y - lastTap.y) < 28
      lastTap = { t: now, x: p.x, y: p.y }
      const hit = hitPin(p.x, p.y)
      if (isDouble) {
        const spot = hit >= 0 ? pins[hit].city : surfacePoint(p.x, p.y)
        if (spot) {
          flyTo(spot.lat, spot.lon)
          tgt.dist = tgt.dist < 2.2 ? DEFAULT_DIST : Math.max(MIN_DIST, tgt.dist * 0.55)
        }
        return
      }
      if (hit >= 0) select(hit, now, true)
      else {
        selectedIdx = -1
        setSelected(-1)
      }
    }

    const onCancel = (e) => {
      pointers.delete(e.pointerId)
      drag = null
      pinch = null
      canvas.style.cursor = 'grab'
    }

    const onWheel = (e) => {
      e.preventDefault()
      markInteraction()
      const unit = e.deltaMode === 1 ? 16 : 1
      tgt.dist = THREE.MathUtils.clamp(tgt.dist * Math.exp(e.deltaY * unit * 0.0013), MIN_DIST, MAX_DIST)
    }

    const onKey = (e) => {
      const step = 9 * (tgt.dist / DEFAULT_DIST)
      switch (e.key) {
        case 'ArrowLeft':
          tgt.lon -= step
          break
        case 'ArrowRight':
          tgt.lon += step
          break
        case 'ArrowUp':
          tgt.lat = Math.min(82, tgt.lat + step)
          break
        case 'ArrowDown':
          tgt.lat = Math.max(-82, tgt.lat - step)
          break
        case '+':
        case '=':
          tgt.dist = Math.max(MIN_DIST, tgt.dist * 0.85)
          break
        case '-':
        case '_':
          tgt.dist = Math.min(MAX_DIST, tgt.dist / 0.85)
          break
        default:
          return
      }
      e.preventDefault()
      markInteraction()
    }

    canvas.addEventListener('pointerdown', onDown)
    canvas.addEventListener('pointermove', onMove)
    canvas.addEventListener('pointerup', onUp)
    canvas.addEventListener('pointercancel', onCancel)
    canvas.addEventListener('wheel', onWheel, { passive: false })
    wrap.addEventListener('keydown', onKey)

    /* ----- frame loop ----- */
    const camPos = new THREE.Vector3()
    const chipPos = { x: 0, y: 0, facing: 0 }
    let raf = 0
    let running = false
    let last = 0
    let t0 = 0
    let sunClock = 0

    const frame = (now) => {
      raf = requestAnimationFrame(frame)
      const dt = Math.min(0.05, (now - last) / 1000 || 0.016)
      last = now
      const time = (now - t0) / 1000

      // Momentum after a flick.
      if (!drag && (Math.abs(vel.lon) > 0.05 || Math.abs(vel.lat) > 0.05)) {
        tgt.lon += vel.lon * dt
        tgt.lat = THREE.MathUtils.clamp(tgt.lat + vel.lat * dt, -82, 82)
        const decay = Math.exp(-dt * 3.4)
        vel.lon *= decay
        vel.lat *= decay
      }

      // Slow, real-direction spin when nobody is touching it.
      if (!reduceMotion && !drag && pointers.size === 0 && now - lastInteract > 6000 && now > introUntil) {
        tgt.lon -= 2.6 * (tgt.dist / DEFAULT_DIST) * dt
      }

      const intro = now < introUntil
      const kMove = intro ? 1.7 : 13
      const kZoom = intro ? 1.7 : 8
      const fMove = 1 - Math.exp(-kMove * dt)
      cur.lon += (tgt.lon - cur.lon) * fMove
      cur.lat += (tgt.lat - cur.lat) * fMove
      cur.dist += (tgt.dist - cur.dist) * (1 - Math.exp(-kZoom * dt))

      latLonToVec3(cur.lat, cur.lon, cur.dist, camPos)
      camera.position.copy(camPos)
      camera.up.set(0, 1, 0)
      camera.lookAt(0, 0, 0)
      earthMat.uniforms.uCam.value.copy(camPos)

      // Refresh the sun position every minute or so.
      if (now - sunClock > 60000) {
        sunClock = now
        sun.copy(sunDirection())
      }

      // Pins keep a steady on-screen size while zooming.
      const pinScale = THREE.MathUtils.clamp((cur.dist - 1) / (DEFAULT_DIST - 1), 0.38, 1.3)
      pins.forEach((pin, i) => {
        const isSel = i === selectedIdx
        const s = pinScale * (isSel ? 1.45 : 1)
        pin.group.scale.setScalar(s)
        pin.dotMat.color.set(isSel ? '#ffffff' : SIGNAL)
        const p = reduceMotion ? 0.25 : (time * 0.42 + pin.phase) % 1
        const ringScale = 1 + p * 2.6
        pin.ring.scale.setScalar(ringScale)
        pin.ringMat.opacity = (isSel ? 0.7 : 0.38) * (1 - p) * (1 - p)
      })

      // Comets between cities.
      const grow = Math.min(1, (now - arcsBornAt) / 1000)
      arcs.forEach((a) => {
        a.mat.uniforms.uTime.value = reduceMotion ? 0 : time
        if (!reduceMotion) a.mat.uniforms.uGrow.value = 1 - Math.pow(1 - grow, 3)
      })

      // Selected-city label follows its pin.
      const chip = chipRef.current
      if (chip) {
        if (selectedIdx >= 0) {
          projectPin(pins[selectedIdx], chipPos)
          const vis = THREE.MathUtils.clamp((chipPos.facing - 0.04) / 0.12, 0, 1)
          const x = THREE.MathUtils.clamp(chipPos.x, 74, Math.max(74, w - 74))
          const y = Math.max(chipPos.y, 64)
          chip.style.transform = `translate3d(${x}px, ${y}px, 0)`
          chip.style.opacity = String(vis)
        } else {
          chip.style.opacity = '0'
        }
      }

      renderer.render(scene, camera)
    }

    const start = () => {
      if (running) return
      running = true
      last = performance.now()
      raf = requestAnimationFrame(frame)
    }
    const stop = () => {
      running = false
      cancelAnimationFrame(raf)
    }
    apiRef.current = { start, stop }

    manager.onLoad = () => {
      t0 = performance.now()
      introUntil = reduceMotion ? 0 : t0 + 2600
      select(0, t0)
      setReady(true)
      start()
    }

    return () => {
      apiRef.current = null
      stop()
      ro.disconnect()
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointermove', onMove)
      canvas.removeEventListener('pointerup', onUp)
      canvas.removeEventListener('pointercancel', onCancel)
      canvas.removeEventListener('wheel', onWheel)
      wrap.removeEventListener('keydown', onKey)
      clearArcs()
      pins.forEach((p) => {
        p.dotMat.dispose()
        p.ringMat.dispose()
      })
      pinDotGeo.dispose()
      pinRingGeo.dispose()
      earthGeo.dispose()
      atmoGeo.dispose()
      earthMat.dispose()
      atmoMat.dispose()
      dayTex.dispose()
      nightTex.dispose()
      waterTex.dispose()
      renderer.dispose()
      if (canvas.parentNode === wrap) wrap.removeChild(canvas)
    }
    // The scene is built once; `paused` is handled by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Stop drawing while the panel is flipped away (phones) so it costs nothing.
  useEffect(() => {
    const api = apiRef.current
    if (!api) return
    if (paused) api.stop()
    else if (ready) api.start()
  }, [paused, ready])

  const city = selected >= 0 ? CITIES[selected] : null
  const coarse = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches

  return (
    <div
      ref={wrapRef}
      tabIndex={0}
      role="application"
      aria-label="Interactive 3D globe. Drag or use the arrow keys to rotate, scroll, pinch or use plus and minus to zoom."
      className={`relative min-h-[11rem] flex-1 select-none transition-opacity duration-700 motion-reduce:transition-none ${
        ready ? 'opacity-100' : 'opacity-0'
      }`}
    >
      <div
        ref={chipRef}
        className="pointer-events-none absolute left-0 top-0 z-10 will-change-transform"
        style={{ opacity: 0, transform: 'translate3d(-999px,-999px,0)' }}
      >
        {city && (
          <div className="-translate-x-1/2 -translate-y-[calc(100%+16px)] whitespace-nowrap rounded-lg border border-line bg-surface-hi/95 px-3 py-2 shadow-lg backdrop-blur">
            <p className="font-display text-sm font-semibold leading-tight text-paper">{city.name}</p>
            <p className="mt-0.5 text-xs text-muted">
              {city.country}, {localTime(city.tz)}
            </p>
          </div>
        )}
      </div>

      <p
        className={`pointer-events-none absolute inset-x-0 bottom-0 text-center text-xs text-muted transition-opacity duration-700 ${
          interacted ? 'opacity-0' : 'opacity-100'
        }`}
        aria-hidden="true"
      >
        {coarse ? 'Drag to spin, pinch to zoom.' : 'Drag to spin, scroll to zoom.'}
      </p>
    </div>
  )
}
