// Entry point: `npm start`. App Service sets PORT; API_BASE_URL comes from
// Terraform outputs (the API app's private hostname).
import { createApp } from './app.js';

const port = Number(process.env.PORT || process.env.WEBSITES_PORT || 8080);
const app = createApp();

app.listen(port, () => {
  const api = process.env.API_BASE_URL ? `proxying /api to ${process.env.API_BASE_URL}` : 'API_BASE_URL not set: /api answers 503';
  console.log(`tax-credit-copilot web listening on ${port}; ${api}`);
});
