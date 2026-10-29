import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { SocketProvider } from './context/SocketContext.jsx'
import { NotificationProvider } from './context/NotificationContext.jsx'
import { CallProvider } from './context/CallContext.jsx'
import { GroupCallProvider } from './context/GroupCallContext.jsx'
import { ToastProvider } from './context/ToastContext.jsx'
import { ThemeProvider } from './context/ThemeContext.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <SocketProvider>
              <NotificationProvider>
                <CallProvider>
                  <GroupCallProvider>
                    <App />
                  </GroupCallProvider>
                </CallProvider>
              </NotificationProvider>
            </SocketProvider>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
