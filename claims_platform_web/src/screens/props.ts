import type { ClientDetail, User } from "../types";

export interface ClientScreenProps {
  client: ClientDetail;
  user: User;
  /** Reload the client header (stage, readiness) after an action. */
  refresh: () => Promise<void> | void;
  /** Changes whenever the client's state changes, so screens can reload their own data. */
  stamp: string;
}
