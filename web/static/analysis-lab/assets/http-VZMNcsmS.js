import{c as u}from"./index-C78KOEFu.js";import{r as o,j as f}from"./client-D1ZVDB-N.js";/**
 * @license lucide-react v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=u("Camera",[["path",{d:"M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z",key:"1tc9qg"}],["circle",{cx:"12",cy:"13",r:"3",key:"1vg3eu"}]]);/**
 * @license lucide-react v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const w=u("Save",[["path",{d:"M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z",key:"1c8476"}],["path",{d:"M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7",key:"1ydtos"}],["path",{d:"M7 3v4a1 1 0 0 0 1 1h7",key:"t51u73"}]]),d=o.createContext(null),h=8e3;async function l(){const t=await fetch("/api/dev/system/info",{cache:"no-store"});let e={};try{e=await t.json()}catch{}if(!t.ok){const n=e;throw new Error(n.detail||`HTTP ${t.status}`)}return e}function S({children:t}){const[e,n]=o.useState(null),[i,r]=o.useState(null),a=o.useCallback(async()=>{try{r(null);const s=await l();n(s)}catch(s){r(s instanceof Error?s.message:String(s))}},[]);o.useEffect(()=>{a();const s=window.setInterval(()=>void a(),h);return()=>window.clearInterval(s)},[a]);const c=o.useMemo(()=>({info:e,error:i,refresh:a}),[e,i,a]);return f.jsx(d.Provider,{value:c,children:t})}function I(){const t=o.useContext(d);if(!t)throw new Error("useSystemInfo must be used within SystemInfoProvider");return t}async function y(t,e={}){const{cache:n,...i}=e,r={headers:{"Content-Type":"application/json"},...i};n!==void 0&&Object.assign(r,{cache:n});const a=await fetch(t,r);let c={};try{c=await a.json()}catch{}if(!a.ok){const s=c;throw new Error(s.detail||`HTTP ${a.status}`)}return c}async function g(t,e={}){const n=t.startsWith("/api/debug/")?t.replace("/api/debug/","/api/dev/debug/"):t;return y(n,e)}export{m as C,w as S,g as a,S as b,y as r,I as u};
