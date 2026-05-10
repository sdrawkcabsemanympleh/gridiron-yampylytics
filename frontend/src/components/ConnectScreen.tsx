import { useEffect, useState } from 'react';
import type { SleeperDraftSummary } from '../types';

interface Props {
  onCreateAndConnect: (draftId: string, sleeperUserId: string) => void;
  error: string | null;
  isConnecting: boolean;
}

const CURRENT_YEAR = new Date().getFullYear();
const SEASONS = Array.from({ length: 7 }, (_, i) => CURRENT_YEAR - i);
const RECENT_USERS_KEY = 'yampgm_recent_users';
const LAST_USER_KEY = 'yampgm_last_user';
const RECENT_DRAFTS_KEY = 'yampgm_recent_drafts';
const MAX_RECENT = 5;

interface SavedUser { userId: string; displayName: string; username: string }

function loadRecentUsers(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_USERS_KEY) ?? '[]') as string[];
  } catch {
    return [];
  }
}

function saveRecentUser(username: string): void {
  const recent = [username, ...loadRecentUsers().filter((u) => u !== username)].slice(0, MAX_RECENT);
  localStorage.setItem(RECENT_USERS_KEY, JSON.stringify(recent));
}

function loadLastUser(): SavedUser | null {
  try {
    return JSON.parse(localStorage.getItem(LAST_USER_KEY) ?? 'null') as SavedUser | null;
  } catch {
    return null;
  }
}

function saveLastUser(user: SavedUser): void {
  localStorage.setItem(LAST_USER_KEY, JSON.stringify(user));
}

function loadRecentDrafts(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_DRAFTS_KEY) ?? '[]') as string[];
  } catch {
    return [];
  }
}

function saveRecentDraft(draftId: string): void {
  const recent = [draftId, ...loadRecentDrafts().filter((d) => d !== draftId)].slice(0, MAX_RECENT);
  localStorage.setItem(RECENT_DRAFTS_KEY, JSON.stringify(recent));
}

async function resolveSleeperUser(usernameOrId: string): Promise<{ userId: string; displayName: string }> {
  const cleaned = usernameOrId.replace(/^@+/, '');
  const isNumericId = /^\d+$/.test(cleaned);
  const url = isNumericId
    ? `https://api.sleeper.app/v1/user/${cleaned}`
    : `https://api.sleeper.app/v1/user/${encodeURIComponent(cleaned)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Sleeper user "${cleaned}" not found.`);
  const data = await res.json() as { user_id?: string; display_name?: string; username?: string };
  if (!data.user_id) throw new Error(`Could not resolve user ID for "${cleaned}".`);
  return { userId: data.user_id, displayName: data.display_name ?? data.username ?? usernameOrId };
}

async function fetchDrafts(userId: string): Promise<SleeperDraftSummary[]> {
  const results = await Promise.all(
    SEASONS.map((season) =>
      fetch(`https://api.sleeper.app/v1/user/${userId}/drafts/nfl/${season}`)
        .then((r) => (r.ok ? (r.json() as Promise<SleeperDraftSummary[]>) : []))
        .catch(() => [] as SleeperDraftSummary[]),
    ),
  );
  const STATUS_ORDER: Record<string, number> = { drafting: 0, pre_draft: 1, complete: 2 };
  return results
    .flat()
    .filter((d) => d.type === 'snake' && (d.status !== 'pre_draft' || d.season === String(CURRENT_YEAR)))
    .sort((a, b) => {
      const statusDiff = (STATUS_ORDER[a.status] ?? 3) - (STATUS_ORDER[b.status] ?? 3);
      if (statusDiff !== 0) return statusDiff;
      // Within same status, most recent first
      return (b.start_time ?? 0) - (a.start_time ?? 0);
    });
}

const STATUS_BADGE: Record<string, string> = {
  drafting: 'bg-emerald-900/50 text-emerald-400 border-emerald-700',
  pre_draft: 'bg-sky-900/50 text-sky-400 border-sky-700',
  complete: 'bg-slate-800 text-slate-500 border-slate-700',
};

function DraftRow({ draft, onSelect }: { draft: SleeperDraftSummary; onSelect: (id: string) => void }) {
  const badge = STATUS_BADGE[draft.status] ?? 'bg-slate-800 text-slate-500 border-slate-700';
  const teams = draft.settings.teams ?? '?';
  const rounds = draft.settings.rounds ?? '?';
  const label = draft.status === 'drafting' ? 'Live' : draft.status === 'pre_draft' ? 'Upcoming' : 'Complete';
  const date = draft.start_time ? new Date(draft.start_time).toLocaleDateString() : null;

  return (
    <button
      onClick={() => onSelect(draft.draft_id)}
      className="w-full text-left flex items-center justify-between px-3 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-500 transition-colors"
    >
      <div>
        <div className="text-sm text-slate-200">
          {draft.season} season · {teams} teams · {rounds} rounds
        </div>
        <div className="text-xs text-slate-500 mt-0.5 font-mono">
          {date ? date : draft.draft_id}
        </div>
      </div>
      <span className={`text-xs font-semibold px-2 py-0.5 rounded border shrink-0 ml-2 ${badge}`}>
        {label}
      </span>
    </button>
  );
}

function ManualDraftEntry({
  userId,
  onConnect,
  disabled,
}: {
  userId: string;
  onConnect: (draftId: string, userId: string) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [draftId, setDraftId] = useState('');
  const [recentDrafts] = useState<string[]>(loadRecentDrafts);

  const handleSubmit = (id: string = draftId.trim()) => {
    if (!id) return;
    saveRecentDraft(id);
    onConnect(id, userId);
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-xs text-slate-600 hover:text-slate-400 transition-colors text-center w-full"
      >
        Don't see your draft? Enter ID manually →
      </button>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Draft ID"
          value={draftId}
          onChange={(e) => setDraftId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          autoFocus
          disabled={disabled}
          className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-600 disabled:opacity-50"
        />
        <button
          onClick={() => handleSubmit()}
          disabled={!draftId.trim() || disabled}
          className="bg-emerald-700 hover:bg-emerald-600 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors shrink-0"
        >
          Go
        </button>
      </div>
      {recentDrafts.length > 0 && (
        <div>
          <div className="text-xs text-slate-600 mb-1.5">Recent mock drafts</div>
          <div className="flex flex-wrap gap-1.5">
            {recentDrafts.map((id) => (
              <button
                key={id}
                onClick={() => handleSubmit(id)}
                disabled={disabled}
                className="text-xs px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-400 hover:border-emerald-700 hover:text-emerald-400 transition-colors disabled:opacity-50 font-mono"
              >
                {id}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

type Step = 'username' | 'pick_draft';

export function ConnectScreen({ onCreateAndConnect, error, isConnecting }: Props) {
  const lastUser = loadLastUser();
  const [step, setStep] = useState<Step>(lastUser ? 'pick_draft' : 'username');
  const [usernameInput, setUsernameInput] = useState('');
  const [resolvedUserId, setResolvedUserId] = useState(lastUser?.userId ?? '');
  const [displayName, setDisplayName] = useState(lastUser?.displayName ?? '');
  const [drafts, setDrafts] = useState<SleeperDraftSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [stepError, setStepError] = useState<string | null>(null);
  const [recentUsers] = useState<string[]>(loadRecentUsers);

  // Auto-fetch drafts when restoring last user
  useEffect(() => {
    if (lastUser && step === 'pick_draft' && drafts.length === 0 && !loading) {
      setLoading(true);
      fetchDrafts(lastUser.userId)
        .then(setDrafts)
        .catch(() => setDrafts([]))
        .finally(() => setLoading(false));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLookup = async (username: string = usernameInput) => {
    if (!username.trim() || loading) return;
    setUsernameInput(username);
    setLoading(true);
    setStepError(null);
    try {
      const { userId, displayName: name } = await resolveSleeperUser(username.trim());
      const found = await fetchDrafts(userId);
      const cleaned = username.trim().replace(/^@+/, '');
      setResolvedUserId(userId);
      setDisplayName(name);
      setDrafts(found);
      saveRecentUser(cleaned);
      saveLastUser({ userId, displayName: name, username: cleaned });
      setStep('pick_draft');
    } catch (err) {
      setStepError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const displayError = stepError ?? (step === 'pick_draft' ? error : null);

  if (step === 'username') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-slate-100">YampGM</h1>
          <p className="text-slate-500 text-sm mt-1">Draft assistant</p>
        </div>

        <div className="w-full max-w-xs space-y-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Sleeper username or user ID</label>
            <input
              type="text"
              placeholder="your_username"
              value={usernameInput}
              onChange={(e) => { setUsernameInput(e.target.value); setStepError(null); }}
              onKeyDown={(e) => e.key === 'Enter' && handleLookup()}
              disabled={loading}
              autoFocus
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-600 disabled:opacity-50"
            />
          </div>

          {recentUsers.length > 0 && (
            <div>
              <div className="text-xs text-slate-600 mb-1.5">Recent</div>
              <div className="flex flex-wrap gap-1.5">
                {recentUsers.map((u) => (
                  <button
                    key={u}
                    onClick={() => handleLookup(u)}
                    disabled={loading}
                    className="text-xs px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-400 hover:border-emerald-700 hover:text-emerald-400 transition-colors disabled:opacity-50"
                  >
                    {u}
                  </button>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => handleLookup()}
            disabled={!usernameInput.trim() || loading}
            className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg px-3 py-2 text-sm font-semibold transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Looking up...
              </>
            ) : (
              'Find my drafts'
            )}
          </button>
        </div>

        {stepError && <p className="text-red-400 text-sm text-center max-w-xs">{stepError}</p>}
      </div>
    );
  }

  // step === 'pick_draft'
  return (
    <div className="flex-1 flex flex-col px-4 py-6 gap-4 overflow-hidden">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-slate-200 font-semibold">{displayName}</div>
          <div className="text-slate-600 text-xs font-mono">{resolvedUserId}</div>
        </div>
        <button
          onClick={() => { setStep('username'); setStepError(null); }}
          className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
        >
          Switch user
        </button>
      </div>

      {drafts.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-slate-600 text-sm">
          No snake drafts found.
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-2">
          <div className="text-xs text-slate-600 mb-1">{drafts.length} draft{drafts.length !== 1 ? 's' : ''} found</div>
          {drafts.map((d) => (
            <DraftRow
              key={d.draft_id}
              draft={d}
              onSelect={isConnecting ? () => {} : (id) => onCreateAndConnect(id, resolvedUserId)}
            />
          ))}
        </div>
      )}

      <ManualDraftEntry
        userId={resolvedUserId}
        onConnect={onCreateAndConnect}
        disabled={isConnecting}
      />

      {isConnecting && (
        <div className="flex items-center justify-center gap-2 text-slate-400 text-sm py-2">
          <div className="w-3.5 h-3.5 border-2 border-slate-600 border-t-slate-300 rounded-full animate-spin" />
          Connecting...
        </div>
      )}

      {displayError && <p className="text-red-400 text-sm text-center">{displayError}</p>}
    </div>
  );
}
