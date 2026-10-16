import assert from 'node:assert/strict';
import {summarizeTaskClusters as summarize} from '/work/kairn/src/bench/pilotClusterDiagnostics.ts';

const pair=(taskId:string,blockId:string,signedTotalTokenDelta:number)=>({taskId,blockId,signedTotalTokenDelta});
const options={seed:17,samples:2000};
const empty=summarize({pairRows:[]},options);
assert.equal(empty.schemaVersion,'codex-pilot-task-clusters.v1');
assert.equal(empty.pairCount,0);assert.equal(empty.taskCount,0);
assert.equal(empty.aggregateSignedTotalTokenDelta,0);
assert.equal(empty.medianSignedTotalTokenDelta,null);
assert.equal(empty.clusteredMedianCi95,null);
const single=summarize({pairRows:[pair('a','1',-10),pair('a','2',20)]},options);
assert.equal(single.taskCount,1);assert.equal(single.pairCount,2);
assert.equal(single.aggregateSignedTotalTokenDelta,10);
assert.equal(single.medianSignedTotalTokenDelta,5);
assert.equal(single.clusteredMedianCi95,null);
const rows=[];
for(let task=0;task<3;task++)for(let repeat=0;repeat<20;repeat++)
 rows.push(pair('task-'+task,`${task}-${repeat}`,task===2?100:-100));
const before=JSON.stringify(rows);
const value=summarize({pairRows:rows},options);
assert.equal(value.taskCount,3);assert.equal(value.pairCount,60);
assert.equal(value.aggregateSignedTotalTokenDelta,-2000);
assert.equal(value.medianSignedTotalTokenDelta,-100);
assert.equal(value.clusteredMedianCi95?.method,'task_cluster_bootstrap');
assert.equal(value.clusteredMedianCi95?.samples,2000);
assert.equal(value.clusteredMedianCi95?.lower,-100);
assert.equal(value.clusteredMedianCi95?.upper,100,'IID repeat resampling loses task dependence');
assert.deepEqual(value,summarize({pairRows:[...rows].reverse()},options));
assert.equal(JSON.stringify(rows),before,'input must be unchanged');
assert.deepEqual(value.tasks.map(x=>x.taskId),['task-2','task-0','task-1']);
assert.equal(value.tasks.reduce((s,x)=>s+x.totalTokenDelta,0),-2000);
for(const bad of [[pair('a','x',1),pair('b','x',2)],[pair('','x',1)],
 [pair('a','',1)],[pair('a','x',NaN)],[pair('a','x',Infinity)]])
 assert.throws(()=>summarize({pairRows:bad},options));
for(const samples of [0,-1,1.5])assert.throws(()=>summarize({pairRows:rows},{seed:17,samples}));
console.log(JSON.stringify({checks:22,passed:true,independentBehavior:true}));
