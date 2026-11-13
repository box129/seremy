import { chosen } from "./barrel.js";
export function Child() {
  return <span>{chosen("child")}</span>;
}
