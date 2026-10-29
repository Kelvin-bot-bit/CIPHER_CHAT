import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext.jsx'
import { useSocket } from '../context/SocketContext.jsx'
import Sidebar from '../components/layout/Sidebar.jsx'
import ChatList from '../components/chat/ChatList.jsx'
import ChatWindow from '../components/chat/ChatWindow.jsx'
import FriendsPanel from '../components/friends/FriendsPanel.jsx'
import GroupsPanel from '../components/groups/GroupsPanel.jsx'
import FilesPanel from '../components/files/FilesPanel.jsx'
import StatusPanel from '../components/status/StatusPanel.jsx'
import FileUploadModal from '../components/files/FileUploadModal.jsx'
import GroupDetailsModal from '../components/groups/GroupDetailsModal.jsx'
import ProfileModal from '../components/profile/ProfileModal.jsx'
import SessionUnlock from '../components/common/SessionUnlock.jsx'
import IncomingCallModal from '../components/call/IncomingCallModal.jsx'
import ActiveCallScreen from '../components/call/ActiveCallScreen.jsx'
import IncomingGroupCallModal from '../components/call/IncomingGroupCallModal.jsx'
import GroupCallScreen from '../components/call/GroupCallScreen.jsx'

// Fallback interval for refreshing per-chat unread badges when the socket
// isn't connected. When it is connected, 'new_message' triggers an
// immediate refresh instead of waiting for this.
const UNREAD_POLL_MS = 20000

export default function ChatPage() {
  const { isLocked, touchActivity, sessionPassword } = useAuth()
  const { socket, connected } = useSocket()
  const [tab, setTab] = useState('chats')
  const [activeChat, setActiveChat] = useState(null)
  const [friends, setFriends] = useState([])
  const [groups, setGroups] = useState([])
  const [loadingChats, setLoadingChats] = useState(true)
  const [unreadByChat, setUnreadByChat] = useState({})
  const [uploadOpen, setUploadOpen] = useState(false)
  const [groupInfoOpen, setGroupInfoOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)

  const loadChats = useCallback(async () => {
    setLoadingChats(true)
    try {
      // We hit /friends/list and /groups/my-groups directly (rather than the
      // combined /users/contacts) so the field names here — group_name,
      // group_picture, member_count — line up with what FriendsPanel and
      // GroupsPanel already expect from those same endpoints. /users/contacts
      // returns a differently-shaped group object (name/picture instead of
      // group_name/group_picture), which would otherwise need its own mapping.
      const [friendsRes, groupsRes] = await Promise.all([
        api.get('/friends/list'),
        api.get('/groups/my-groups'),
      ])
      setFriends(friendsRes.data.friends || [])
      setGroups(groupsRes.data.groups || [])
    } catch {
      // Non-fatal — the Friends/Groups tabs load their own data independently
      // and will still work even if this combined view fails.
    } finally {
      setLoadingChats(false)
    }
  }, [])

  const loadUnread = useCallback(async () => {
    if (!sessionPassword) return
    try {
      const res = await api.get('/messages/unread-by-chat')
      const map = {}
      ;(res.data.chats || []).forEach((c) => {
        map[`${c.chat_type}_${c.chat_id}`] = c.unread_count
      })
      setUnreadByChat(map)
    } catch {
      // Non-fatal — badges just won't update this cycle, next poll/socket
      // event will retry.
    }
  }, [sessionPassword])

  useEffect(() => {
    loadChats()
  }, [loadChats])

  useEffect(() => {
    loadUnread()
  }, [loadUnread])

  // Real-time: refresh badges the moment a new message arrives, rather
  // than waiting for the fallback poll.
  useEffect(() => {
    if (!socket) return
    const onNewMessage = () => loadUnread()
    socket.on('new_message', onNewMessage)
    return () => socket.off('new_message', onNewMessage)
  }, [socket, loadUnread])

  // Fallback poll only while the socket is down.
  useEffect(() => {
    if (connected) return
    const id = setInterval(loadUnread, UNREAD_POLL_MS)
    return () => clearInterval(id)
  }, [connected, loadUnread])

  useEffect(() => {
    const onActivity = () => touchActivity()
    window.addEventListener('keydown', onActivity)
    window.addEventListener('click', onActivity)
    return () => {
      window.removeEventListener('keydown', onActivity)
      window.removeEventListener('click', onActivity)
    }
  }, [touchActivity])

  const openChat = (chat) => {
    setActiveChat(chat)
    setTab('chats')
    // Optimistic: opening a chat makes the backend mark its messages read
    // as a side effect of fetching history (see MessageService.get_chat_
    // messages), so the badge will genuinely clear server-side within a
    // moment — zero it locally right away instead of waiting on that.
    setUnreadByChat((prev) => {
      const key = `${chat.type}_${chat.id}`
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const handleGroupLeftOrDeleted = () => {
    setActiveChat(null)
    loadChats()
  }

  const renderPanel = () => {
    switch (tab) {
      case 'status':
        return <StatusPanel />
      case 'friends':
        return <FriendsPanel onOpenChat={openChat} onFriendsChanged={setFriends} />
      case 'groups':
        return <GroupsPanel friends={friends} onOpenChat={openChat} />
      case 'files':
        return <FilesPanel />
      default:
        return (
          <ChatList
            friends={friends}
            groups={groups}
            activeChat={activeChat}
            onSelect={openChat}
            loading={loadingChats}
            unreadByChat={unreadByChat}
          />
        )
    }
  }

  const showListOnMobile = !activeChat || tab !== 'chats'
  const activeGroup =
    activeChat?.type === 'group' ? { id: activeChat.id, group_name: activeChat.name } : null
  const totalUnread = Object.values(unreadByChat).reduce((sum, n) => sum + n, 0)

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-ink">
      <div className={`h-full w-full lg:block ${showListOnMobile ? 'block' : 'hidden'} lg:w-auto`}>
        <Sidebar
          tab={tab}
          onTabChange={setTab}
          onOpenProfile={() => setProfileOpen(true)}
          chatsBadge={totalUnread}
        >
          {renderPanel()}
        </Sidebar>
      </div>

      <div className={`h-full min-w-0 flex-1 ${showListOnMobile ? 'hidden' : 'block'} lg:block`}>
        {isLocked ? (
          <SessionUnlock />
        ) : activeChat ? (
          <ChatWindow
            key={`${activeChat.type}-${activeChat.id}`}
            chat={activeChat}
            onBack={() => setActiveChat(null)}
            onOpenFiles={() => setUploadOpen(true)}
            onOpenGroupInfo={() => setGroupInfoOpen(true)}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="font-display text-xl font-semibold text-paper">Select a conversation</p>
            <p className="text-sm text-muted">Pick a friend or group from the left to start chatting securely.</p>
          </div>
        )}
      </div>

      <FileUploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} />
      <GroupDetailsModal
        open={groupInfoOpen}
        onClose={() => setGroupInfoOpen(false)}
        group={activeGroup}
        friends={friends}
        onLeft={handleGroupLeftOrDeleted}
        onDeleted={handleGroupLeftOrDeleted}
      />
      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
      <IncomingCallModal />
      <ActiveCallScreen />
      <IncomingGroupCallModal />
      <GroupCallScreen />
    </div>
  )
}
