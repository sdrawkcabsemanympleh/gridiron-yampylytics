import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  DraftEvent,
  PickMadeEvent,
  PickRecord,
  PlayerInfo,
  RecommendationItem,
  SessionState,
} from '../types';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface DraftSessionHook {
  session: SessionState | null;
  recommendations: RecommendationItem[];
  recommendationsForPick: number | null;
  connectionStatus: ConnectionStatus;
  error: string | null;
  /** Create a new session via POST, then open the WebSocket. */
  createAndConnect: (draftId: string, sleeperUserId: string) => void;
  /** Attach to an existing session via GET, then open the WebSocket. */
  connect: (draftId: string) => void;
  disconnect: () => void;
}

function applyPickEvent(session: SessionState, event: PickMadeEvent): SessionState {
  const newPick: PickRecord = {
    overall_pick: event.overall_pick,
    round: event.round,
    pick_in_round: event.pick_in_round,
    manager_id: event.manager_id,
    player_id: event.player_id,
    player_name: event.player_name,
    position: event.position,
    team: event.team,
  };
  const updatedRoster: PlayerInfo[] = event.is_user_pick
    ? [
        ...session.user_roster,
        {
          player_id: event.player_id,
          name: event.player_name,
          position: event.position,
          team: event.team,
          projected_points: 0,
          adp: 0,
        },
      ]
    : session.user_roster;
  return {
    ...session,
    picks: [...session.picks, newPick],
    current_pick: event.current_pick,
    is_user_turn: event.is_user_turn,
    user_roster: updatedRoster,
  };
}

function openWebSocket(
  draftId: string,
  draftIdRef: React.MutableRefObject<string | null>,
  wsRef: React.MutableRefObject<WebSocket | null>,
  setConnectionStatus: (s: ConnectionStatus) => void,
  setError: (e: string | null) => void,
  setSession: React.Dispatch<React.SetStateAction<SessionState | null>>,
  setRecommendations: React.Dispatch<React.SetStateAction<RecommendationItem[]>>,
  setRecommendationsForPick: React.Dispatch<React.SetStateAction<number | null>>,
): void {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${protocol}://${window.location.host}/api/sessions/${draftId}/ws`);
  wsRef.current = ws;

  ws.onopen = () => setConnectionStatus('connected');

  ws.onmessage = (msg) => {
    let event: DraftEvent;
    try {
      event = JSON.parse(msg.data) as DraftEvent;
    } catch {
      return;
    }
    if (event.type === 'pick_made') {
      const pickEvt = event as PickMadeEvent;
      setSession((prev) => (prev ? applyPickEvent(prev, pickEvt) : prev));
      setRecommendations(pickEvt.candidates);
      setRecommendationsForPick(null);
    } else if (event.type === 'recommendations') {
      setRecommendations(event.candidates);
      setRecommendationsForPick(event.for_pick);
    } else if (event.type === 'draft_complete') {
      setSession((prev) => (prev ? { ...prev, is_complete: true } : prev));
      ws.close();
    }
  };

  ws.onerror = () => {
    setConnectionStatus('error');
    setError('WebSocket connection failed.');
  };

  ws.onclose = () => {
    if (draftIdRef.current === draftId) {
      setConnectionStatus('disconnected');
    }
  };
}

export function useDraftSession(): DraftSessionHook {
  const [session, setSession] = useState<SessionState | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [recommendationsForPick, setRecommendationsForPick] = useState<number | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const draftIdRef = useRef<string | null>(null);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    draftIdRef.current = null;
    setSession(null);
    setRecommendations([]);
    setRecommendationsForPick(null);
    setConnectionStatus('disconnected');
    setError(null);
  }, []);

  const connect = useCallback(
    (draftId: string) => {
      disconnect();
      draftIdRef.current = draftId;
      setError(null);
      setConnectionStatus('connecting');

      fetch(`/api/sessions/${draftId}`)
        .then((res) => {
          if (!res.ok) throw new Error(`Session not found (${res.status})`);
          return res.json() as Promise<SessionState>;
        })
        .then((state) => {
          setSession(state);
          setRecommendations([]);
          setRecommendationsForPick(null);
          openWebSocket(
            draftId, draftIdRef, wsRef,
            setConnectionStatus, setError,
            setSession, setRecommendations, setRecommendationsForPick,
          );
        })
        .catch((err: Error) => {
          setConnectionStatus('error');
          setError(err.message);
        });
    },
    [disconnect],
  );

  const createAndConnect = useCallback(
    (draftId: string, sleeperUserId: string) => {
      disconnect();
      draftIdRef.current = draftId;
      setError(null);
      setConnectionStatus('connecting');

      fetch('/api/sessions/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft_id: draftId, sleeper_user_id: sleeperUserId }),
      })
        .then(async (res) => {
          if (res.status === 409) {
            // Session already exists — fall through to GET
            return fetch(`/api/sessions/${draftId}`).then((r) => {
              if (!r.ok) throw new Error(`Failed to load existing session (${r.status})`);
              return r.json() as Promise<SessionState>;
            });
          }
          if (!res.ok) {
            const body = await res.json().catch(() => ({})) as { detail?: string };
            throw new Error(body.detail ?? `Server error (${res.status})`);
          }
          return res.json() as Promise<SessionState>;
        })
        .then((state) => {
          setSession(state);
          setRecommendations([]);
          setRecommendationsForPick(null);
          openWebSocket(
            draftId, draftIdRef, wsRef,
            setConnectionStatus, setError,
            setSession, setRecommendations, setRecommendationsForPick,
          );
        })
        .catch((err: Error) => {
          setConnectionStatus('error');
          setError(err.message);
        });
    },
    [disconnect],
  );

  // Clean up on unmount
  useEffect(() => () => disconnect(), [disconnect]);

  return {
    session,
    recommendations,
    recommendationsForPick,
    connectionStatus,
    error,
    createAndConnect,
    connect,
    disconnect,
  };
}
