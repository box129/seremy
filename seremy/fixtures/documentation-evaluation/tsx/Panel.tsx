import { normalize as clean } from './helper';

export function Panel() {
  return <section>{clean('ok')}</section>;
}

export function launch() { return Panel(); }
