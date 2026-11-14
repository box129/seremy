import * as api from './helper'
import { forwarded } from './barrel'
const run = api.make
export const onClick = () => run()
export function App() { return <button onClick={onClick}>{api.leaf() + forwarded()}</button> }
