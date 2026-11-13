import { chosen } from "./barrel.js";
import { Child } from "./Child.jsx";
export function App() {
  return <main><Child value={chosen("é🦊")} /></main>;
}
export function invoke() { return App(); }
