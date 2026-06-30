import { useDeferredValue, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { FixedSizeList, type ListChildComponentProps } from "react-window";
import {
  connectSession,
  createSession,
  disconnectSession,
  getApiBase,
  listSessions,
} from "./lib/api";
import type {
  DltMessagePayload,
  SessionCreateRequest,
  SessionInfo,
  SessionStats,
  StatsPayload,
  StreamEvent,
} from "./lib/types";

const MAX_MESSAGES = 2000;
const LOG_ROW_HEIGHT = 56;

const defaultForm: SessionCreateRequest = {
  transport: "tcp",
  host: "127.0.0.1",
  port: 3490,
  ecu_id: "ECU1",
  multicast_group: "",
  interface_ip: "",
};

function deriveWsUrl(sessionId: string): string {
  const explicitBase = import.meta.env.VITE_WS_BASE as string | undefined;
  if (explicitBase) {
    return `${explicitBase.replace(/\/$/, "")}/${sessionId}`;
  }

  const apiBase = new URL(getApiBase());
  apiBase.protocol = apiBase.protocol === "https:" ? "wss:" : "ws:";
  apiBase.pathname = `/stream/${sessionId}`;
  apiBase.search = "";
  apiBase.hash = "";
  return apiBase.toString();
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleTimeString();
}

function matchesFilter(message: DltMessagePayload, searchText: string, level: string): boolean {
  const levelMatch = level === "all" || message.log_level.toLowerCase() === level;
  if (!levelMatch) {
    return false;
  }

  if (!searchText) {
    return true;
  }

  const normalized = searchText.toLowerCase();
  return [
    message.ecu_id,
    message.apid,
    message.ctid,
    message.msg_type,
    message.log_level,
    message.payload_text,
  ].some((part) => part.toLowerCase().includes(normalized));
}

interface RowData {
  messages: DltMessagePayload[];
  onSelect: (message: DltMessagePayload) => void;
  selectedMessageId: string | null;
}

function messageId(message: DltMessagePayload): string {
  return `${message.timestamp_sec}:${message.mcnt}:${message.apid}:${message.ctid}`;
}

function LogRow({ data, index, style }: ListChildComponentProps<RowData>) {
  const message = data.messages[index];
  const selected = data.selectedMessageId === messageId(message);

  return (
    <button
      className={`log-row${selected ? " selected" : ""}`}
      style={style}
      onClick={() => data.onSelect(message)}
      type="button"
    >
      <span>{message.ecu_id}</span>
      <span>{message.apid}</span>
      <span>{message.ctid}</span>
      <span>{message.log_level}</span>
      <span>{message.payload_text}</span>
    </button>
  );
}

export default function App() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, DltMessagePayload[]>>({});
  const [stats, setStats] = useState<Record<string, SessionStats>>({});
  const [drawerMessage, setDrawerMessage] = useState<DltMessagePayload | null>(null);
  const [searchText, setSearchText] = useState("");
  const [levelFilter, setLevelFilter] = useState("all");
  const [createForm, setCreateForm] = useState<SessionCreateRequest>(defaultForm);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [busySessionId, setBusySessionId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [streamStatus, setStreamStatus] = useState("idle");
  const reconnectRef = useRef<number | null>(null);

  const deferredSearchText = useDeferredValue(searchText.trim());
  const selectedSession = sessions.find((session) => session.session_id === selectedSessionId) ?? null;
  const selectedStats = selectedSessionId ? stats[selectedSessionId] : undefined;
  const sessionMessages = selectedSessionId ? messages[selectedSessionId] ?? [] : [];

  const filteredMessages = useMemo(
    () => sessionMessages.filter((message) => matchesFilter(message, deferredSearchText, levelFilter)),
    [deferredSearchText, levelFilter, sessionMessages],
  );

  async function refreshSessions() {
    const nextSessions = await listSessions();
    setSessions(nextSessions);
    if (!selectedSessionId && nextSessions.length > 0) {
      setSelectedSessionId(nextSessions[0].session_id);
    }
    if (selectedSessionId && !nextSessions.some((session) => session.session_id === selectedSessionId)) {
      setSelectedSessionId(nextSessions[0]?.session_id ?? null);
    }
  }

  useEffect(() => {
    refreshSessions().catch((error: unknown) => {
      setErrorText(error instanceof Error ? error.message : "Failed to load sessions.");
    });
  }, []);

  const handleStreamEvent = useEffectEvent((event: StreamEvent) => {
    if (event.type === "message") {
      setMessages((current) => {
        const existing = current[event.session_id] ?? [];
        const next = [...existing, event.payload as DltMessagePayload].slice(-MAX_MESSAGES);
        return {
          ...current,
          [event.session_id]: next,
        };
      });
      return;
    }

    if (event.type === "stats") {
      const payload = event.payload as StatsPayload;
      setStats((current) => {
        const previous = current[event.session_id];
        const now = Date.now();
        const elapsedSec = previous?.lastStatsAt ? (now - previous.lastStatsAt) / 1000 : 0;
        const delta = previous ? payload.messages_received - previous.messagesReceived : 0;

        return {
          ...current,
          [event.session_id]: {
            messagesReceived: payload.messages_received,
            bytesReceived: payload.bytes_received,
            decodeErrors: payload.decode_errors,
            receiveRate: elapsedSec > 0 ? delta / elapsedSec : 0,
            clientLagMs: Math.max(0, now - Date.parse(event.timestamp)),
            lastStatsAt: now,
          },
        };
      });
      return;
    }

    if (event.type === "connection_state") {
      const nextState = event.payload.state;
      setSessions((current) =>
        current.map((session) =>
          session.session_id === event.session_id
            ? {
                ...session,
                state: nextState,
                updated_at: event.timestamp,
              }
            : session,
        ),
      );
      setStreamStatus(nextState);
      return;
    }

    if (event.type === "error") {
      setErrorText(event.payload.detail);
    }
  });

  useEffect(() => {
    if (!selectedSessionId) {
      setStreamStatus("idle");
      return undefined;
    }

    let active = true;
    let socket: WebSocket | null = null;

    const connect = () => {
      setStreamStatus("connecting");
      socket = new WebSocket(deriveWsUrl(selectedSessionId));

      socket.onopen = () => {
        setStreamStatus("subscribed");
      };

      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as StreamEvent;
        handleStreamEvent(event);
      };

      socket.onerror = () => {
        setStreamStatus("error");
      };

      socket.onclose = () => {
        if (!active) {
          return;
        }
        setStreamStatus("reconnecting");
        reconnectRef.current = window.setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      active = false;
      if (reconnectRef.current !== null) {
        window.clearTimeout(reconnectRef.current);
      }
      socket?.close();
    };
  }, [handleStreamEvent, selectedSessionId]);

  async function handleCreateSession() {
    setIsSubmitting(true);
    setErrorText(null);

    try {
      const session = await createSession({
        ...createForm,
        multicast_group: createForm.multicast_group || undefined,
        interface_ip: createForm.interface_ip || undefined,
      });
      await refreshSessions();
      setSelectedSessionId(session.session_id);
      setCreateForm(defaultForm);
    } catch (error: unknown) {
      setErrorText(error instanceof Error ? error.message : "Failed to create session.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSessionAction(sessionId: string, action: "connect" | "disconnect") {
    setBusySessionId(sessionId);
    setErrorText(null);

    try {
      if (action === "connect") {
        await connectSession(sessionId);
      } else {
        await disconnectSession(sessionId);
      }
      await refreshSessions();
    } catch (error: unknown) {
      setErrorText(error instanceof Error ? error.message : `Failed to ${action} session.`);
    } finally {
      setBusySessionId(null);
    }
  }

  return (
    <div className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <header className="hero">
        <div>
          <p className="eyebrow">Phase 5 · Web UI MVP</p>
          <h1>DLT Viewer Live Bridge Console</h1>
          <p className="hero-copy">
            Create ECU sessions, drive TCP or UDP ingestion, inspect live DLT traffic,
            and watch stream health in one browser surface.
          </p>
        </div>

        <div className="hero-meta">
          <div>
            <span>API</span>
            <strong>{getApiBase()}</strong>
          </div>
          <div>
            <span>Stream</span>
            <strong>{streamStatus}</strong>
          </div>
          <div>
            <span>Visible messages</span>
            <strong>{filteredMessages.length}</strong>
          </div>
        </div>
      </header>

      {errorText ? <div className="error-banner">{errorText}</div> : null}

      <main className="layout-grid">
        <section className="panel panel-form">
          <div className="panel-header">
            <h2>Connections</h2>
            <p>Create a bridge session and route it into the live stream.</p>
          </div>

          <div className="form-grid">
            <label>
              <span>Transport</span>
              <select
                value={createForm.transport}
                onChange={(event) =>
                  setCreateForm((current) => ({
                    ...current,
                    transport: event.target.value as SessionCreateRequest["transport"],
                  }))
                }
              >
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
              </select>
            </label>

            <label>
              <span>Host</span>
              <input
                value={createForm.host}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, host: event.target.value }))
                }
              />
            </label>

            <label>
              <span>Port</span>
              <input
                min={1}
                max={65535}
                type="number"
                value={createForm.port}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, port: Number(event.target.value) }))
                }
              />
            </label>

            <label>
              <span>ECU ID</span>
              <input
                value={createForm.ecu_id}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, ecu_id: event.target.value }))
                }
              />
            </label>

            <label>
              <span>Multicast group</span>
              <input
                placeholder="Optional for UDP"
                value={createForm.multicast_group}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, multicast_group: event.target.value }))
                }
              />
            </label>

            <label>
              <span>Interface IP</span>
              <input
                placeholder="Optional for multicast"
                value={createForm.interface_ip}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, interface_ip: event.target.value }))
                }
              />
            </label>
          </div>

          <button className="primary-button" disabled={isSubmitting} onClick={handleCreateSession} type="button">
            {isSubmitting ? "Creating..." : "Create session"}
          </button>

          <div className="sessions-list">
            {sessions.map((session) => {
              const isSelected = selectedSessionId === session.session_id;
              const isBusy = busySessionId === session.session_id;
              const canConnect = session.state !== "connected" && session.state !== "connecting";

              return (
                <article
                  className={`session-card${isSelected ? " active" : ""}`}
                  key={session.session_id}
                  onClick={() => setSelectedSessionId(session.session_id)}
                >
                  <div>
                    <div className="session-card-topline">
                      <strong>{session.ecu_id}</strong>
                      <span className={`state-pill state-${session.state}`}>{session.state}</span>
                    </div>
                    <p>
                      {session.transport.toUpperCase()} · {session.host}:{session.port}
                    </p>
                    <small>Created {formatDate(session.created_at)}</small>
                  </div>

                  <div className="session-actions">
                    <button
                      className="secondary-button"
                      disabled={isBusy || !canConnect}
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleSessionAction(session.session_id, "connect");
                      }}
                      type="button"
                    >
                      Connect
                    </button>
                    <button
                      className="ghost-button"
                      disabled={isBusy || canConnect}
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleSessionAction(session.session_id, "disconnect");
                      }}
                      type="button"
                    >
                      Disconnect
                    </button>
                  </div>
                </article>
              );
            })}

            {sessions.length === 0 ? <p className="empty-state">No sessions created yet.</p> : null}
          </div>
        </section>

        <section className="panel panel-stream">
          <div className="panel-header stream-header">
            <div>
              <h2>Live stream</h2>
              <p>
                {selectedSession
                  ? `${selectedSession.ecu_id} · ${selectedSession.transport.toUpperCase()} ${selectedSession.host}:${selectedSession.port}`
                  : "Select a session to subscribe to its stream."}
              </p>
            </div>

            <div className="filter-bar">
              <input
                placeholder="Filter ecu / apid / ctid / payload"
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
              />
              <select value={levelFilter} onChange={(event) => setLevelFilter(event.target.value)}>
                <option value="all">All levels</option>
                <option value="fatal">Fatal</option>
                <option value="error">Error</option>
                <option value="warn">Warn</option>
                <option value="info">Info</option>
                <option value="debug">Debug</option>
                <option value="verbose">Verbose</option>
              </select>
            </div>
          </div>

          <div className="stats-grid">
            <div className="stat-card">
              <span>Receive rate</span>
              <strong>{selectedStats ? `${selectedStats.receiveRate.toFixed(1)} msg/s` : "0.0 msg/s"}</strong>
            </div>
            <div className="stat-card">
              <span>Traffic</span>
              <strong>{selectedStats ? formatBytes(selectedStats.bytesReceived) : "0 B"}</strong>
            </div>
            <div className="stat-card">
              <span>Decode errors</span>
              <strong>{selectedStats?.decodeErrors ?? 0}</strong>
            </div>
            <div className="stat-card">
              <span>Client lag</span>
              <strong>{selectedStats ? `${selectedStats.clientLagMs} ms` : "0 ms"}</strong>
            </div>
          </div>

          <div className="log-table-shell">
            <div className="log-table-head">
              <span>ECU</span>
              <span>APID</span>
              <span>CTID</span>
              <span>Level</span>
              <span>Payload</span>
            </div>

            {filteredMessages.length > 0 ? (
              <FixedSizeList
                className="log-list"
                height={448}
                itemCount={filteredMessages.length}
                itemData={{
                  messages: filteredMessages,
                  onSelect: setDrawerMessage,
                  selectedMessageId: drawerMessage ? messageId(drawerMessage) : null,
                }}
                itemSize={LOG_ROW_HEIGHT}
                width="100%"
              >
                {LogRow}
              </FixedSizeList>
            ) : (
              <div className="empty-state empty-log">
                Live DLT messages will appear here once the selected session starts ingesting.
              </div>
            )}
          </div>
        </section>
      </main>

      <aside className={`drawer${drawerMessage ? " open" : ""}`}>
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Message detail</p>
            <h2>{drawerMessage ? `${drawerMessage.apid}/${drawerMessage.ctid}` : "Select a log row"}</h2>
          </div>
          <button className="ghost-button" onClick={() => setDrawerMessage(null)} type="button">
            Close
          </button>
        </div>

        {drawerMessage ? (
          <dl className="detail-grid">
            <div>
              <dt>ECU</dt>
              <dd>{drawerMessage.ecu_id}</dd>
            </div>
            <div>
              <dt>Message count</dt>
              <dd>{drawerMessage.mcnt}</dd>
            </div>
            <div>
              <dt>Message type</dt>
              <dd>{drawerMessage.msg_type}</dd>
            </div>
            <div>
              <dt>Level</dt>
              <dd>{drawerMessage.log_level}</dd>
            </div>
            <div>
              <dt>Verbose</dt>
              <dd>{drawerMessage.verbose ? "true" : "false"}</dd>
            </div>
            <div>
              <dt>Timestamp</dt>
              <dd>{drawerMessage.timestamp_sec}</dd>
            </div>
            <div className="detail-payload">
              <dt>Payload</dt>
              <dd>{drawerMessage.payload_text}</dd>
            </div>
            {drawerMessage.decode_error ? (
              <div className="detail-payload">
                <dt>Decode error</dt>
                <dd>{drawerMessage.decode_error}</dd>
              </div>
            ) : null}
          </dl>
        ) : (
          <p className="empty-state">Pick any message in the stream table for full field inspection.</p>
        )}
      </aside>
    </div>
  );
}