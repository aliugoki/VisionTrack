import { useEffect, useState } from 'react';
import { io, type Socket } from 'socket.io-client';
import { useAuth } from '@/shared/hooks/useAuth';

/**
 * Singleton tenant-wide Socket.IO connection.
 *
 * One socket per browser tab serves every camera and every component that
 * needs realtime events. The socket auto-connects when the user has a
 * valid access token and tears down on logout.
 *
 * The Vite dev proxy forwards /socket.io to the backend at port 8000;
 * in production a reverse proxy does the same. The frontend never needs
 * to know the backend's actual URL.
 */

let socketSingleton: Socket | null = null;
let currentToken: string | null = null;

function ensureSocket(token: string): Socket {
  // If the token changed, tear down the old socket and rebuild.
  if (socketSingleton && currentToken !== token) {
    socketSingleton.disconnect();
    socketSingleton = null;
  }
  if (socketSingleton) return socketSingleton;

  currentToken = token;
  socketSingleton = io({
    path: '/socket.io',
    transports: ['websocket', 'polling'],
    auth: { token },
    // Reconnect aggressively but back off — typical for live monitoring
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 10000,
  });
  return socketSingleton;
}

function teardownSocket() {
  if (socketSingleton) {
    socketSingleton.disconnect();
    socketSingleton = null;
    currentToken = null;
  }
}

export interface SocketStatus {
  socket: Socket | null;
  connected: boolean;
}

/**
 * Returns the live socket and its connected state.
 * Reuses the singleton across all components.
 */
export function useSocket(): SocketStatus {
  const token = useAuth((s) => s.accessToken);
  const [connected, setConnected] = useState(false);
  const [socket, setSocket] = useState<Socket | null>(null);

  useEffect(() => {
    if (!token) {
      teardownSocket();
      setSocket(null);
      setConnected(false);
      return;
    }

    const s = ensureSocket(token);
    setSocket(s);
    setConnected(s.connected);

    const onConnect = () => setConnected(true);
    const onDisconnect = () => setConnected(false);
    s.on('connect', onConnect);
    s.on('disconnect', onDisconnect);

    return () => {
      s.off('connect', onConnect);
      s.off('disconnect', onDisconnect);
      // NOTE: we deliberately do NOT call s.disconnect() here. The socket
      // is a singleton shared across components; the last component to
      // unmount shouldn't tear it down. Logout triggers teardown via the
      // `!token` branch above.
    };
  }, [token]);

  return { socket, connected };
}
