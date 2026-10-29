import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useAuth } from './AuthContext.jsx'
import { useSocket } from './SocketContext.jsx'
import { useToast } from './ToastContext.jsx'

const CallContext = createContext(null)

// STUN resolves each side's public address so two peers can usually
// connect directly. TURN is the fallback relay for when they can't —
// restrictive/corporate NATs, symmetric firewalls, or two peers behind
// the same router without NAT hairpinning (common when testing two
// accounts on the same local network).
const ICE_SERVERS = [
  { urls: 'stun:stun.l.google.com:19302' },
  {
    urls: 'turn:free.expressturn.com:3478',
    username: '000000002106767095',
    credential: 'SzHP3wy6iAIkOFze8HzihBKbSuM=',
  },
]

export function CallProvider({ children }) {
  const { user, accessToken } = useAuth()
  const { socket, connected } = useSocket()
  const toast = useToast()

  // 'idle' | 'calling' (outgoing, ringing at their end) | 'ringing'
  // (incoming, awaiting our accept/reject) | 'active'
  const [callState, setCallState] = useState('idle')
  const [callType, setCallType] = useState('video')
  const [peerUser, setPeerUser] = useState(null)
  const [localStream, setLocalStream] = useState(null)
  const [remoteStream, setRemoteStream] = useState(null)
  const [micEnabled, setMicEnabled] = useState(true)
  const [cameraEnabled, setCameraEnabled] = useState(true)
  const [callDurationSec, setCallDurationSec] = useState(0)

  const pcRef = useRef(null)
  const callIdRef = useRef(null)
  const pendingOfferRef = useRef(null) // stored while ringing, used only if accepted
  const pendingCandidatesRef = useRef([]) // ICE candidates that arrive before remote description is set
  const durationTimerRef = useRef(null)

  const cleanup = useCallback(() => {
    pcRef.current?.close()
    pcRef.current = null
    localStream?.getTracks().forEach((t) => t.stop())
    setLocalStream(null)
    setRemoteStream(null)
    setPeerUser(null)
    setCallState('idle')
    setMicEnabled(true)
    setCameraEnabled(true)
    setCallDurationSec(0)
    callIdRef.current = null
    pendingOfferRef.current = null
    pendingCandidatesRef.current = []
    clearInterval(durationTimerRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localStream])

  const emitSignal = useCallback(
    (event, payload) => {
      if (!socket || !accessToken) return
      socket.emit(event, { ...payload, token: accessToken })
    },
    [socket, accessToken],
  )

  const buildPeerConnection = useCallback(() => {
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS })

    pc.onicecandidate = (e) => {
      // Read the ref live, at emit time — not a callId captured when this
      // connection was created. For the caller specifically, the real
      // call_id isn't known until the 'call_initiated' ack arrives
      // (server-minted, after the offer is sent), which can easily be
      // after ICE gathering has already started producing candidates.
      // Capturing a fixed value here meant every one of the caller's
      // candidates sent before that ack went out tagged call_id: null,
      // which the backend silently drops (no matching call in
      // _active_calls) — candidates lost, and connections that depend on
      // trickle ICE could fail to ever establish.
      if (e.candidate && callIdRef.current) {
        emitSignal('call_ice_candidate', { call_id: callIdRef.current, candidate: e.candidate })
      }
    }
    pc.ontrack = (e) => {
      setRemoteStream((prev) => {
        const stream = prev || new MediaStream()
        stream.addTrack(e.track)
        return stream
      })
    }
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'failed') {
        toast.error('Call connection failed — the other side may be behind a restrictive network')
        endCall()
      }
    }

    pcRef.current = pc
    return pc
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emitSignal, toast])

  const getLocalMedia = useCallback(async (type) => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: type === 'video',
    })
    setLocalStream(stream)
    setCameraEnabled(type === 'video')
    return stream
  }, [])

  const startCall = useCallback(
    async (peer, type = 'video') => {
      if (callState !== 'idle') {
        toast.error('Finish or end your current call first')
        return
      }
      if (!connected) {
        toast.error('Not connected — check your connection and try again')
        return
      }
      try {
        setPeerUser(peer)
        setCallType(type)
        setCallState('calling')

        const stream = await getLocalMedia(type)
        const pc = buildPeerConnection()
        stream.getTracks().forEach((track) => pc.addTrack(track, stream))

        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        emitSignal('call_offer', { to_user_id: peer.id, offer, call_type: type })
      } catch (err) {
        console.error('startCall failed:', err)
        toast.error(
          err.name === 'NotAllowedError'
            ? 'Camera/microphone permission was denied'
            : 'Could not start the call',
        )
        cleanup()
      }
    },
    [callState, connected, getLocalMedia, buildPeerConnection, emitSignal, toast, cleanup],
  )

  const acceptCall = useCallback(async () => {
    const offerData = pendingOfferRef.current
    if (!offerData) return
    try {
      setCallState('active')
      const stream = await getLocalMedia(offerData.call_type)
      const pc = buildPeerConnection()
      stream.getTracks().forEach((track) => pc.addTrack(track, stream))

      await pc.setRemoteDescription(offerData.offer)
      for (const candidate of pendingCandidatesRef.current) {
        await pc.addIceCandidate(candidate).catch(() => {})
      }
      pendingCandidatesRef.current = []

      const answer = await pc.createAnswer()
      await pc.setLocalDescription(answer)

      emitSignal('call_answer', { call_id: offerData.call_id, answer })
    } catch (err) {
      console.error('acceptCall failed:', err)
      toast.error(
        err.name === 'NotAllowedError'
          ? 'Camera/microphone permission was denied'
          : 'Could not join the call',
      )
      emitSignal('call_end', { call_id: offerData.call_id })
      cleanup()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getLocalMedia, buildPeerConnection, emitSignal, toast, cleanup])

  const rejectCall = useCallback(() => {
    if (callIdRef.current) emitSignal('call_reject', { call_id: callIdRef.current })
    cleanup()
  }, [emitSignal, cleanup])

  const endCall = useCallback(() => {
    if (callIdRef.current) emitSignal('call_end', { call_id: callIdRef.current })
    cleanup()
  }, [emitSignal, cleanup])

  const toggleMic = useCallback(() => {
    if (!localStream) return
    const next = !micEnabled
    localStream.getAudioTracks().forEach((t) => (t.enabled = next))
    setMicEnabled(next)
  }, [localStream, micEnabled])

  const toggleCamera = useCallback(() => {
    if (!localStream || callType !== 'video') return
    const next = !cameraEnabled
    localStream.getVideoTracks().forEach((t) => (t.enabled = next))
    setCameraEnabled(next)
  }, [localStream, cameraEnabled, callType])

  // --- Socket signaling listeners ---
  useEffect(() => {
    if (!socket) return

    const onOffer = (data) => {
      if (callState !== 'idle') {
        // Busy — let the caller know rather than silently ignoring.
        socket.emit('call_end', { call_id: data.call_id, token: accessToken })
        return
      }
      callIdRef.current = data.call_id
      pendingOfferRef.current = data
      setPeerUser(data.from_user)
      setCallType(data.call_type)
      setCallState('ringing')
    }

    const onCallInitiated = (data) => {
      // The server mints call_id after receiving the offer and acks it
      // straight back to the caller specifically so outgoing ICE
      // candidates have somewhere to attach as soon as they start
      // gathering — see the comment in buildPeerConnection's
      // onicecandidate handler above for why this can't wait for the
      // answer to arrive.
      callIdRef.current = data.call_id
    }

    const onAnswer = async (data) => {
      const pc = pcRef.current
      if (!pc) return
      callIdRef.current = data.call_id
      await pc.setRemoteDescription(data.answer)
      for (const candidate of pendingCandidatesRef.current) {
        await pc.addIceCandidate(candidate).catch(() => {})
      }
      pendingCandidatesRef.current = []
      setCallState('active')
    }

    const onIceCandidate = async (data) => {
      const pc = pcRef.current
      if (!pc) return
      if (!pc.remoteDescription) {
        pendingCandidatesRef.current.push(data.candidate)
        return
      }
      await pc.addIceCandidate(data.candidate).catch(() => {})
    }

    const onBusy = () => {
      toast.error(`${peerUser?.full_name || peerUser?.username || 'They'} are on another call`)
      cleanup()
    }

    const onRejected = () => {
      toast.info(`${peerUser?.full_name || peerUser?.username || 'Call'} declined`)
      cleanup()
    }

    const onEnded = () => {
      cleanup()
    }

    const onCallError = (data) => {
      toast.error(data.message || 'Call error')
      cleanup()
    }

    socket.on('call_offer', onOffer)
    socket.on('call_initiated', onCallInitiated)
    socket.on('call_answer', onAnswer)
    socket.on('call_ice_candidate', onIceCandidate)
    socket.on('call_busy', onBusy)
    socket.on('call_rejected', onRejected)
    socket.on('call_ended', onEnded)
    socket.on('call_error', onCallError)

    return () => {
      socket.off('call_offer', onOffer)
      socket.off('call_initiated', onCallInitiated)
      socket.off('call_answer', onAnswer)
      socket.off('call_ice_candidate', onIceCandidate)
      socket.off('call_busy', onBusy)
      socket.off('call_rejected', onRejected)
      socket.off('call_ended', onEnded)
      socket.off('call_error', onCallError)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [socket, callState, peerUser, accessToken, cleanup, toast])

  // Call duration timer, active only while the call is actually active.
  useEffect(() => {
    if (callState !== 'active') return
    const start = Date.now()
    durationTimerRef.current = setInterval(() => {
      setCallDurationSec(Math.floor((Date.now() - start) / 1000))
    }, 1000)
    return () => clearInterval(durationTimerRef.current)
  }, [callState])

  // If the socket drops entirely mid-call, there's no signaling channel
  // left to end it cleanly with — better to end the call locally than
  // leave the UI stuck showing an "active" call that can never actually
  // hang up or receive further signaling.
  useEffect(() => {
    if (!connected && callState !== 'idle') {
      toast.error('Connection lost — call ended')
      cleanup()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected])

  const value = {
    callState,
    callType,
    peerUser,
    localStream,
    remoteStream,
    micEnabled,
    cameraEnabled,
    callDurationSec,
    startCall,
    acceptCall,
    rejectCall,
    endCall,
    toggleMic,
    toggleCamera,
  }

  return <CallContext.Provider value={value}>{children}</CallContext.Provider>
}

export function useCall() {
  const ctx = useContext(CallContext)
  if (!ctx) throw new Error('useCall must be used within CallProvider')
  return ctx
}
