import external from "external-lib";
import { unknown } from "./absent.js";
const callable = () => 1;
function stable() { return 1; }
stable = callable;
export function limitations(client) {
  callable();
  client.fetch();
  external();
  unknown();
  stable();
}
export const callback = () => stable();
