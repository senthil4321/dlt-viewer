export type Transport = "tcp" | "udp";
export type SessionState =
  | "created"
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

export interface SessionInfo {
  session_id: string;
  transport: Transport;
  host: string;
  port: number;
  ecu_id: string;
  multicast_group: string | null;
  interface_ip: string | null;
  state: SessionState;
  created_at: string;
  updated_at: string;
}

export interface SessionCreateRequest {
  transport: Transport;
  host: string;
  port: number;
  ecu_id: string;
  multicast_group?: string;
  interface_ip?: string;
}

export interface DltMessagePayload {
  ecu_id: string;
  apid: string;
  ctid: string;
  msg_type: string;
  log_level: string;
  verbose: boolean;
  mcnt: number;
  timestamp_sec: number;
  payload_text: string;
  decode_error?: string | null;
}

export interface ConnectionStatePayload {
  state: SessionState;
  transport: Transport;
  host: string;
  port: number;
  ecu_id: string;
  error?: string;
}

export interface StatsPayload {
  messages_received: number;
  bytes_received: number;
  decode_errors: number;
}

export interface ErrorPayload {
  code: string;
  detail: string;
}

export interface EventEnvelope<TPayload = Record<string, unknown>> {
  type: "heartbeat" | "message" | "connection_state" | "stats" | "error";
  timestamp: string;
  session_id: string;
  seq: number;
  payload: TPayload;
}

export type StreamEvent =
  | EventEnvelope<DltMessagePayload>
  | EventEnvelope<ConnectionStatePayload>
  | EventEnvelope<StatsPayload>
  | EventEnvelope<ErrorPayload>
  | EventEnvelope<{ message: string }>;

export interface SessionStats {
  messagesReceived: number;
  bytesReceived: number;
  decodeErrors: number;
  receiveRate: number;
  clientLagMs: number;
  lastStatsAt: number | null;
}