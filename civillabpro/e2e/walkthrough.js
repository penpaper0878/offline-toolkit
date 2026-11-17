// End-to-end walkthrough in a real browser: register, create a project, design a beam, save,
// download the report / schedule / drawing, switch theme, search, use the calculator, reload.
//
//   1. start the API and the web client (see README.md)
//   2. node e2e/walkthrough.js <folder for screenshots> [base URL, default http://127.0.0.1:5173]
//
// Needs the `playwright` package and a Chromium it can launch. Exits non-zero on any failure
// and prints every browser console error it saw.
const { chromium } = require('playwright');
const out = process.argv[2] || '.';
const BASE = process.argv[3] || process.env.BASE || 'http://127.0.0.1:5173';
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: Number(process.env.DSF || 1), acceptDownloads: true, colorScheme: 'light' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  const shot = (n) => page.screenshot({ path: `${out}/${n}.png` });
  const step = (s) => console.log('STEP', s);

  await page.goto(BASE + '/');
  await page.waitForURL('**/login');
  await shot('01-login');
  step('register');
  await page.getByRole('button', { name: /Create an organisation/ }).click();
  await page.getByLabel('Organisation', { exact: true }).fill('Sahyadri Consultants');
  await page.getByLabel('Your name').fill('Asha Kulkarni');
  await page.getByLabel('Email').fill(`asha${Date.now()}@sahyadri.example`);
  await page.getByLabel('Password').fill('Structure2026');
  await page.getByRole('button', { name: 'Create organisation' }).click();
  await page.getByRole('heading', { name: /Welcome, Asha/ }).waitFor();
  await shot('02-dashboard-empty');

  step('project');
  await page.getByRole('toolbar').getByRole('button', { name: 'New project' }).click();
  await page.getByLabel('Job number').fill(`SC-${Date.now() % 100000}`);
  await page.getByLabel('Project name').fill('Ward 12 Community Hall');
  await page.getByLabel('Client').fill('Municipal Corporation');
  await page.getByLabel('Location').fill('Rajkot');
  await shot('03-new-project');
  await page.getByRole('button', { name: 'Create project' }).click();
  await page.getByRole('heading', { name: /Ward 12 Community Hall/ }).waitFor();

  step('workspace');
  await page.getByRole('link', { name: /New RCC beam/ }).click();
  await page.getByText('All checks', { exact: false }).first().waitFor({ timeout: 15000 }).catch(() => {});
  await page.getByText('3-T16').first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(600);
  await shot('04-workspace');

  step('edit');
  const depth = page.locator('#pg-depth_mm');
  await depth.fill('500');
  await page.getByText('4-T12').first().waitFor({ timeout: 10000 });
  await page.keyboard.press('Control+s');
  await page.waitForURL('**/designs/*', { timeout: 10000 });
  await page.getByText(/saved/i).first().waitFor();
  await page.waitForTimeout(500);
  await shot('05-saved');

  step('exports');
  for (const [id, ext] of [['pdf', '.pdf'], ['xlsx', '.xlsx'], ['dxf', '.dxf']]) {
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.locator(`[data-ribbon="${id}"]`).click()]);
    const p = `${out}/export${ext}`;
    await dl.saveAs(p);
    console.log('download', dl.suggestedFilename(), require('fs').statSync(p).size);
  }

  step('panels');
  await page.getByText('Checks', { exact: true }).first().click();
  await page.waitForTimeout(300);
  await shot('06-checks');
  await page.getByText('Bar schedule', { exact: true }).first().click();
  await page.waitForTimeout(300);
  await page.getByText('Longitudinal section', { exact: true }).first().click();
  await page.waitForTimeout(400);
  await shot('07-bbs-elevation');

  step('invalid input');
  await page.locator('#pg-width_mm').fill('50');
  await page.getByText('Not less than 150.').waitFor();
  await shot('08-invalid');
  await page.locator('#pg-width_mm').fill('230');

  step('dark + palette');
  await page.keyboard.press('Alt+t');
  await page.waitForTimeout(400);
  await page.getByText('Calculation', { exact: true }).first().click();
  await page.getByText('Section', { exact: true }).first().click();
  await page.waitForTimeout(300);
  await shot('09-dark-workspace');
  await page.keyboard.press('Control+k');
  await page.getByPlaceholder(/Search projects and designs/).fill('B1');
  await page.getByRole('option', { name: /Beam B1/ }).waitFor({ timeout: 8000 });
  await shot('10-palette');
  await page.keyboard.press('Escape');
  await page.keyboard.press('Alt+c');
  await page.getByLabel('Expression').fill('0.87*500*bar(16,3)/1000');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  await shot('11-calculator');
  await page.keyboard.press('Alt+c');

  step('dashboard with data');
  await page.keyboard.press('Alt+1');
  await page.getByRole('heading', { name: /Welcome/ }).waitFor();
  await page.waitForTimeout(700);
  await shot('12-dashboard-dark');
  await page.keyboard.press('Alt+t');
  await page.waitForTimeout(400);
  await shot('13-dashboard-light');
  await page.goto(BASE + '/admin/users');
  await page.getByRole('heading', { name: 'Users and roles' }).waitFor();
  await page.waitForTimeout(400);
  await shot('14-users');

  step('reload restores session');
  await page.reload();
  await page.getByRole('heading', { name: 'Users and roles' }).waitFor({ timeout: 10000 });

  console.log('ERRORS', errors.length);
  for (const e of errors) console.log('  ', e.slice(0, 300));
  await browser.close();
  if (errors.length) process.exit(1);
})().catch((e) => { console.error('FAILED', e.message.slice(0, 600)); process.exit(1); });
