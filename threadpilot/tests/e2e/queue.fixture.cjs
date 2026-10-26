/* UI-only fixture. Queue arithmetic is tested against hand calculations in the backend suite. */
const snapshot=require('./snapshot.fixture.json');
module.exports={business_date:snapshot.today,available:true,schedule:{version:0,priority:[]},
 assumptions:['UI fixture: current orders, same capacity before and after.'],
 orders:snapshot.orders.filter(o=>o.status==='IN_PROGRESS').map(o=>({...o,
  risk:{level:o.due_date<snapshot.today?'overdue':'medium',reason:'Queue fixture for browser interactions.',best_date:o.due_date}}))};
