import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useAuth } from './AuthContext.jsx'
import { useSocket } from './SocketContext.jsx'
import { useToast } from './ToastContext.jsx'

const GroupCallContext = createContext(null)

// Same STUN+TURN setup as the 1:1 CallContext — see its comment for the
// full explanation. For a mesh call this matters more, not less: every
// one of the N-1 links a participant holds needs its own successful ICE
// negotiation, so a NAT-traversal failure on any single link just drops
// that one person's tile rather than the whole call.
const ICE_SERVERS = [
  { urls: 'stun:stun.l.google.com:19302' },
  {
    urls: 'turn:free.expressturn.com:3478',
    username: '000000002106767095',
    credential: 'SzHP3wy6iAIkOFze8HzihBKbSuM=',
  },
]

export function GroupCallProvider({ children }) {
  const { user, accessToken } = useAuth()
  const { socket, connected } = useSocket()
  const toast = useToast()

  // 'idle' | 'ringing' (incoming invite, not yet joined) | 'active'
  const [callState, setCallState] = useState('idle')
  const [callType, setCallType] = useState('video')
  const [groupInfo, setGroupInfo] = useState(null) // { id, name }
  const [pendingInvite, setPendingInvite] = useState(null) // { call_id, from_user } while ringing
  const [localStream, setLocalStream] = useState(null)
  const [micEnabled, setMicEnabled] = useState(true)
  const [cameraEnabled, setCameraEnabled] = useState(true)
  const [callDurationSec, setCallDurationSec] = useState(0)
  // { [userId]: { user: {id, username, full_name, profile_picture}, stream: MediaStream|null } }
  const [participants, setParticipants] = useState({})

  const callIdRef = useRef(null)
  const localStreamRef = useRef(null) // mirrors localStream for use inside socket callbacks without stale closures
  const pcMapRef = useRef(new Map()) // userId -> RTCPeerConnection
  const pendingCandidatesRef = useRef(new Map()) // userId -> candidate[] queued before that peer's remoteDescription is set
  const durationTimerRef = useRef(null)

  const emitSignal = useCallback(
    (event, payload) => {
      if (!socket || !accessToken) return
      socket.emit(event, { ...payload, token: accessToken })
    },
    [socket, accessToken],
  )

  const closePeer = useCallback((userId) => {
    pcMapRef.current.get(userId)?.close()
    pcMapRef.current.delete(userId)
    pendingCandidatesRef.current.delete(userId)
    setParticipants((prev) => {
      const next = { ...prev }
      delete next[userId]
      return next
    })
  }, [])

  const cleanup = useCallback(() => {
    for (const pc of pcMapRef.current.values()) pc.close()
    pcMapRef.current.clear()
    pendingCandidatesRef.current.clear()
    localStreamRef.current?.getTracks().forEach((t) => t.stop())
    localStreamRef.current = null
    setLocalStream(null)
    setParticipants({})
    setGroupInfo(null)
    setPendingInvite(null)
    setCallState('idle')
    setMicEnabled(true)
    setCameraEnabled(true)
    setCallDurationSec(0)
    callIdRef.current = null
    clearInterval(durationTimerRef.current)
  }, [])

  const getLocalMedia = useCallback(async (type) => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: type === 'video',
    })
    localStreamRef.current = stream
    setLocalStream(stream)
    setCameraEnabled(type === 'video')
    return stream
  }, [])

  // Builds one mesh link. `initiator` controls only whether this side
  // will create the offer — every peer connection is otherwise
  // identical, tracks flow both ways once connected regardless of who
  // proposed it.
  const buildPeerConnection = useCallback(
    (peerId) => {
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS })

      pc.onicecandidate = (e) => {
        if (e.candidate && callIdRef.current) {
          emitSignal('group_call_ice_candidate', {
            call_id: callIdRef.current,
            to_user_id: peerId,
            candidate: e.candidate,
          })
        }
      }
      pc.ontrack = (e) => {
        setParticipants((prev) => {
          const existing = prev[peerId]
          if (!existing) return prev
          const stream = existing.stream || new MediaStream()
          stream.addTrack(e.track)
          return { ...prev, [peerId]: { ...existing, stream } }
        })
      }
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
          closePeer(peerId)
        }
      }

      localStreamRef.current?.getTracks().forEach((track) => pc.addTrack(track, localStreamRef.current))
      pcMapRef.current.set(peerId, pc)
      return pc
    },
    [emitSignal, closePeer],
  )

  const startGroupCall = useCallback(
    async (group, type = 'video') => {
      if (callState !== 'idle') {
        toast.error('Finish or leave your current call first')
        return
      }
      if (!connected) {
        toast.error('Not connected — check your connection and try again')
        return
      }
      try {
        setGroupInfo({ id: group.id, name: group.group_name || group.name })
        setCallType(type)
        setCallState('active')
        await getLocalMedia(type)
        emitSignal('group_call_start', { group_id: group.id, call_type: type })
      } catch (err) {
        console.error('startGroupCall failed:', err)
        toast.error(
          err.name === 'NotAllowedError' ? 'Camera/microphone permission was denied' : 'Could not start the call',
        )
        cleanup()
      }
    },
    [callState, connected, getLocalMedia, emitSignal, toast, cleanup],
  )

  const acceptGroupCallInvite = useCallback(async () => {
    const invite = pendingInvite
    if (!invite) return
    try {
      setCallState('active')
      await getLocalMedia(invite.call_type)
      emitSignal('group_call_join', { call_id: invite.call_id })
    } catch (err) {
      console.error('acceptGroupCallInvite failed:', err)
      toast.error(
        err.name === 'NotAllowedError' ? 'Camera/microphone permission was denied' : 'Could not join the call',
      )
      emitSignal('group_call_leave', { call_id: invite.call_id })
      cleanup()
    }
  }, [pendingInvite, getLocalMedia, emitSignal, toast, cleanup])

  const rejectGroupCallInvite = useCallback(() => {
    if (pendingInvite) emitSignal('group_call_reject', { call_id: pendingInvite.call_id })
    setPendingInvite(null)
    setCallState('idle')
  }, [pendingInvite, emitSignal])

  const leaveGroupCall = useCallback(() => {
    if (callIdRef.current) emitSignal('group_call_leave', { call_id: callIdRef.current })
    cleanup()
  }, [emitSignal, cleanup])

  const toggleMic = useCallback(() => {
    if (!localStreamRef.current) return
    const next = !micEnabled
    localStreamRef.current.getAudioTracks().forEach((t) => (t.enabled = next))
    setMicEnabled(next)
  }, [micEnabled])

  const toggleCamera = useCallback(() => {
    if (!localStreamRef.current || callType !== 'video') return
    const next = !cameraEnabled
    localStreamRef.current.getVideoTracks().forEach((t) => (t.enabled = next))
    setCameraEnabled(next)
  }, [cameraEnabled, callType])

  // --- Socket signaling listeners ---
  useEffect(() => {
    if (!socket) return

    const onIncoming = (data) => {
      if (callState !== 'idle') {
        // Already on a call (1:1 or another group call) — let the
        // inviter's side know rather than leaving them ringing forever.
        // This used to happen with zero visible feedback on this end,
        // which made a stale/incorrectly-"busy" local state (e.g. left
        // over from a call that didn't clean up properly) indistinguishable
        // from the invite never arriving at all — impossible to tell
        // apart without this toast.
        toast.info(`Missed a group call invite from ${data.group_name || 'a group'} — you're already on a call`)
        socket.emit('group_call_reject', { call_id: data.call_id, token: accessToken })
        return
      }
      setPendingInvite(data)
      setGroupInfo({ id: data.group_id, name: data.group_name })
      setCallType(data.call_type)
      setCallState('ringing')
    }

    const onInitiated = (data) => {
      callIdRef.current = data.call_id
    }

    // The server tells a just-joined client who else is already in —
    // this side always initiates to each of them (offer + send), per the
    // one-directional convention that avoids offer glare in a mesh.
    const onExistingParticipants = async (data) => {
      callIdRef.current = data.call_id
      for (const participant of data.participants) {
        setParticipants((prev) => ({ ...prev, [participant.id]: { user: participant, stream: null } }))
        try {
          const pc = buildPeerConnection(participant.id)
          const offer = await pc.createOffer()
          await pc.setLocalDescription(offer)
          emitSignal('group_call_offer', { call_id: data.call_id, to_user_id: participant.id, offer })
        } catch (err) {
          console.error('Failed to connect to existing participant:', err)
          closePeer(participant.id)
        }
      }
    }

    // A new participant joined — just register the tile and wait for
    // their offer; we never initiate towards someone newer than us.
    const onParticipantJoined = (data) => {
      setParticipants((prev) => ({ ...prev, [data.user.id]: { user: data.user, stream: null } }))
    }

    const onOffer = async (data) => {
      try {
        const pc = buildPeerConnection(data.from_user_id)
        await pc.setRemoteDescription(data.offer)
        const queued = pendingCandidatesRef.current.get(data.from_user_id) || []
        for (const candidate of queued) await pc.addIceCandidate(candidate).catch(() => {})
        pendingCandidatesRef.current.delete(data.from_user_id)

        const answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        emitSignal('group_call_answer', { call_id: data.call_id, to_user_id: data.from_user_id, answer })
      } catch (err) {
        console.error('Failed to answer group call offer:', err)
        closePeer(data.from_user_id)
      }
    }

    const onAnswer = async (data) => {
      const pc = pcMapRef.current.get(data.from_user_id)
      if (!pc) return
      await pc.setRemoteDescription(data.answer)
      const queued = pendingCandidatesRef.current.get(data.from_user_id) || []
      for (const candidate of queued) await pc.addIceCandidate(candidate).catch(() => {})
      pendingCandidatesRef.current.delete(data.from_user_id)
    }

    const onIceCandidate = async (data) => {
      const pc = pcMapRef.current.get(data.from_user_id)
      if (!pc || !pc.remoteDescription) {
        const queue = pendingCandidatesRef.current.get(data.from_user_id) || []
        queue.push(data.candidate)
        pendingCandidatesRef.current.set(data.from_user_id, queue)
        return
      }
      await pc.addIceCandidate(data.candidate).catch(() => {})
    }

    const onParticipantLeft = (data) => closePeer(data.user_id)
    const onParticipantDeclined = (data) => {
      // Previously silent — if everyone you invited happened to auto-
      // decline (see onIncoming's comment above for how that can happen
      // invisibly on their end too), the call would just sit there with
      // no participants and no indication anything had gone wrong.
      const declinedUser = data.user || participants[data.user_id]?.user
      toast.info(`${declinedUser?.full_name || declinedUser?.username || 'Someone'} didn't join the call`)
      closePeer(data.user_id)
    }

    // Group failures come on their own event rather than the shared
    // 'call_error' that 1:1 calls use, so a problem with one kind of call
    // doesn't pop an error toast for the other.
    const onGroupCallError = (data) => {
      toast.error(data.message || 'Call error')
      // Until the server has handed us a call id we haven't actually joined
      // anything (starting or joining was refused), so back out of the call
      // screen. Once connected, an error shouldn't tear down a working call.
      if (callState !== 'active' || !callIdRef.current) cleanup()
    }

    // The call finished while this invite was still ringing (everyone who
    // had joined has left), so there is nothing left to join. Without this
    // the incoming-call screen would just sit there forever.
    const onEnded = (data) => {
      if (pendingInvite?.call_id === data.call_id && callIdRef.current !== data.call_id) {
        toast.info('That group call has ended')
        cleanup()
      }
    }

    socket.on('group_call_incoming', onIncoming)
    socket.on('group_call_initiated', onInitiated)
    socket.on('group_call_existing_participants', onExistingParticipants)
    socket.on('group_call_participant_joined', onParticipantJoined)
    socket.on('group_call_offer', onOffer)
    socket.on('group_call_answer', onAnswer)
    socket.on('group_call_ice_candidate', onIceCandidate)
    socket.on('group_call_participant_left', onParticipantLeft)
    socket.on('group_call_participant_declined', onParticipantDeclined)
    socket.on('group_call_ended', onEnded)
    socket.on('group_call_error', onGroupCallError)

    return () => {
      socket.off('group_call_incoming', onIncoming)
      socket.off('group_call_initiated', onInitiated)
      socket.off('group_call_existing_participants', onExistingParticipants)
      socket.off('group_call_participant_joined', onParticipantJoined)
      socket.off('group_call_offer', onOffer)
      socket.off('group_call_answer', onAnswer)
      socket.off('group_call_ice_candidate', onIceCandidate)
      socket.off('group_call_participant_left', onParticipantLeft)
      socket.off('group_call_participant_declined', onParticipantDeclined)
      socket.off('group_call_ended', onEnded)
      socket.off('group_call_error', onGroupCallError)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [socket, callState, pendingInvite, accessToken, buildPeerConnection, closePeer, emitSignal, cleanup, toast])

  useEffect(() => {
    if (callState !== 'active') return
    const start = Date.now()
    durationTimerRef.current = setInterval(() => {
      setCallDurationSec(Math.floor((Date.now() - start) / 1000))
    }, 1000)
    return () => clearInterval(durationTimerRef.current)
  }, [callState])

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
    groupInfo,
    pendingInvite,
    localStream,
    participants,
    micEnabled,
    cameraEnabled,
    callDurationSec,
    startGroupCall,
    acceptGroupCallInvite,
    rejectGroupCallInvite,
    leaveGroupCall,
    toggleMic,
    toggleCamera,
  }

  return <GroupCallContext.Provider value={value}>{children}</GroupCallContext.Provider>
}

export function useGroupCall() {
  const ctx = useContext(GroupCallContext)
  if (!ctx) throw new Error('useGroupCall must be used within GroupCallProvider')
  return ctx
}
