import {getDatabase} from '@netlify/database';
import {handler} from '../../server/netlify/api.mjs';
let pool;
export default handler(()=>pool??=(getDatabase().pool));
