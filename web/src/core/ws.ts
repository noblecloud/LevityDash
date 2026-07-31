// ---- websocket client with reconnect/backoff, mirroring RemoteConnection ----

export type ConnState = 'connecting' | 'connected' | 'disconnected';

export class WsClient {
	onMessage: ((msg: unknown) => void) | null = null;
	onState: ((state: ConnState) => void) | null = null;

	private ws: WebSocket | null = null;
	private closedByUs = false;
	private attempts = 0;
	private reconnectTimer: number | null = null;

	constructor(private url: string) {}

	connect() {
		this.closedByUs = false;
		this.setState('connecting');
		try {
			this.ws = new WebSocket(this.url);
		} catch {
			this.scheduleReconnect();
			return;
		}
		this.ws.onopen = () => {
			this.attempts = 0;
			this.setState('connected');
		};
		this.ws.onmessage = (ev) => {
			try {
				this.onMessage?.(JSON.parse(ev.data));
			} catch {
				// ignore malformed frames
			}
		};
		this.ws.onclose = () => {
			this.ws = null;
			if (!this.closedByUs) this.scheduleReconnect();
		};
		this.ws.onerror = () => this.ws?.close();
	}

	send(obj: unknown) {
		if (this.ws && this.ws.readyState === WebSocket.OPEN) {
			this.ws.send(JSON.stringify(obj));
		}
	}

	private scheduleReconnect() {
		this.setState('disconnected');
		if (this.reconnectTimer != null) return;
		const delay = Math.min(1000 * 2 ** this.attempts, 15000);
		this.attempts++;
		this.reconnectTimer = window.setTimeout(() => {
			this.reconnectTimer = null;
			this.connect();
		}, delay);
	}

	close() {
		this.closedByUs = true;
		if (this.reconnectTimer != null) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}
		this.ws?.close();
	}

	private setState(s: ConnState) {
		this.onState?.(s);
	}
}
