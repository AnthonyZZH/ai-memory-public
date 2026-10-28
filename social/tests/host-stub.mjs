// Intentionally small fake of the services injected by DSH, not an SDK emulator.
export const defineTool = value => value;
export const createUserMessage = value => value;
export const SessionId = value => value;
export const installModelSelection = () => {};
const schema = new Proxy(function(){return schema;},{get:()=>schema});
export default schema;
