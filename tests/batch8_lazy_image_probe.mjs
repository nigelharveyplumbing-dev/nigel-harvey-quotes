import assert from 'node:assert/strict';
import { BrowserOperationTimeout, waitForImageLoad } from './batch8_browser_support.mjs';

// A deliberately off-screen image isolates native lazy loading from the
// application. No article text, records or external services are involved.
export async function verifyLazyImageLifecycle(page, origin, step) {
  const path=origin+'/__batch8_lazy_image_probe';
  await page.route(path,route=>route.fulfill({contentType:'text/html',body:
    '<!doctype html><div style="height:100000px"></div><img loading="lazy" width="960" height="1440" src="/site-images/shower-illustrative.webp" alt="Public illustrative image for browser diagnosis">'}));
  try {
    await step('lazy-probe/navigation',()=>page.goto(path));
    await step('lazy-probe/network-idle',()=>page.waitForLoadState('networkidle'));
    const image=page.locator('img');
    const before=await step('lazy-probe/initial-state',()=>image.evaluate(i=>({loading:i.loading,complete:i.complete,naturalWidth:i.naturalWidth})));
    assert.equal(before.loading,'lazy');assert.equal(before.complete,false);assert.equal(before.naturalWidth,0);
    let timedOut=false;
    try { await step('lazy-probe/decode-before-scroll',()=>image.evaluate(i=>i.decode()),300); }
    catch(error) { if(error instanceof BrowserOperationTimeout)timedOut=true;else throw error; }
    assert(timedOut,'decode must remain pending while this off-screen lazy image is deferred');
    await step('lazy-probe/scroll-into-view',()=>image.scrollIntoViewIfNeeded({timeout:10000}));
    await step('lazy-probe/load-after-scroll',()=>waitForImageLoad(image),8000);
    const decoded=await step('lazy-probe/decode-after-scroll',()=>image.evaluate(async i=>{try{await i.decode();return {ok:true}}catch(e){return {ok:false,error:e.message,src:i.currentSrc,complete:i.complete,width:i.naturalWidth}}}),8000);
    if(!decoded.ok)throw new Error(JSON.stringify(decoded));
    const after=await step('lazy-probe/final-state',()=>image.evaluate(i=>({loading:i.loading,complete:i.complete,naturalWidth:i.naturalWidth})));
    assert.equal(after.loading,'lazy');assert.equal(after.complete,true);assert(after.naturalWidth>0);
    return {before,decodeBeforeScrollTimedOut:timedOut,after};
  } finally { await page.unroute(path); }
}
