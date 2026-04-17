import{c as u}from"./index-DfB_HEYK.js";import{r,j as d}from"./client-D1ZVDB-N.js";/**
 * @license lucide-react v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const w=u("Camera",[["path",{d:"M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z",key:"1tc9qg"}],["circle",{cx:"12",cy:"13",r:"3",key:"1vg3eu"}]]);/**
 * @license lucide-react v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const v=u("Info",[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 16v-4",key:"1dtifu"}],["path",{d:"M12 8h.01",key:"e9boi3"}]]),f=r.createContext(null),l=8e3;async function h(){const t=await fetch("/api/dev/system/info",{cache:"no-store"});let e={};try{e=await t.json()}catch{}if(!t.ok){const o=e;throw new Error(o.detail||`HTTP ${t.status}`)}return e}function I({children:t}){const[e,o]=r.useState(null),[i,a]=r.useState(null),n=r.useCallback(async()=>{try{a(null);const s=await h();o(s)}catch(s){a(s instanceof Error?s.message:String(s))}},[]);r.useEffect(()=>{n();const s=window.setInterval(()=>void n(),l);return()=>window.clearInterval(s)},[n]);const c=r.useMemo(()=>({info:e,error:i,refresh:n}),[e,i,n]);return d.jsx(f.Provider,{value:c,children:t})}function g(){const t=r.useContext(f);if(!t)throw new Error("useSystemInfo must be used within SystemInfoProvider");return t}async function y(t,e={}){const{cache:o,...i}=e,a={headers:{"Content-Type":"application/json"},...i};o!==void 0&&Object.assign(a,{cache:o});const n=await fetch(t,a);let c={};try{c=await n.json()}catch{}if(!n.ok){const s=c;throw new Error(s.detail||`HTTP ${n.status}`)}return c}async function x(t,e={}){const o=t.startsWith("/api/debug/")?t.replace("/api/debug/","/api/dev/debug/"):t;return y(o,e)}export{w as C,v as I,I as S,x as a,y as r,g as u};
