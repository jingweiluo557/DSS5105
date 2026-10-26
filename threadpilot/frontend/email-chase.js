/* Order chase-up entry points share the AI review and confirmed Outlook send. */
(() => {
  draftPage = function(){
    const order=find(params.get('id'));
    if(!order)return head('Order chase-up','Choose an order to prepare a follow-up email.');
    return head('Order chase-up',order.id+' · '+order.customer)+`<section class="card"><h2>Prepare a department email</h2><p>Current department: <strong>${esc(titleCase(order.stage))}</strong></p><p>The draft uses this order's records and the department email in Settings. Review the recipient, subject and message before confirming a real send.</p><div class="actions"><button class="primary" data-order-email="${esc(order.id)}">Generate chase-up</button><a href="#/settings" class="button">Department emails</a></div></section>`;
  };
  document.addEventListener('click',e=>{
    const review=e.target.closest('[data-review-chase]');
    if(review&&!aiBusy){ask('Preview draft '+review.dataset.reviewChase+' for review before sending');return;}
    const order=e.target.closest('[data-order-email]');
    if(order&&!aiBusy){openAIDrawer();ask('Draft a chase-up for '+order.dataset.orderEmail+' to its corresponding department. Show me the draft before sending.');}
  });
  if(route==='draft')render();
})();
