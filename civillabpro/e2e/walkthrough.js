// End-to-end walkthrough in a real browser: register, create a project, design a beam, a column, a slab,
// an isolated and a combined footing, a continuous beam (by coefficients and by elastic analysis), save, export and import a project, back up the database, download each report / schedule / drawing, switch theme, search, use the calculator,
// reload.
//
//   1. start the API, on a fresh database (the backup step needs one organisation alone), and the web client (see README.md)
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
  await page.waitForTimeout(500); // longer than the input debounce: correcting the value must not send the stale one
  await shot('08-invalid');
  await page.locator('#pg-width_mm').fill('230');

  step('dark + palette');
  await page.keyboard.press('Alt+t');
  await page.waitForTimeout(400);
  await page.getByText('Calculation', { exact: true }).first().click();
  await page.getByText('Section A-A', { exact: true }).first().click();
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

  step('column');
  await page.locator('[data-ribbon="project"]').click();
  await page.getByRole('link', { name: /New RCC column/ }).click();
  await page.getByText('12-T12').first().waitFor({ timeout: 15000 });
  await page.getByText('Charts', { exact: true }).first().click();
  await page.getByRole('img', { name: /Interaction about the x axis/ }).waitFor({ timeout: 10000 });
  await page.waitForTimeout(600);
  await shot('c1-column-charts-dark');
  await page.keyboard.press('Control+s');
  await page.waitForURL('**/designs/*', { timeout: 10000 });
  await page.getByText(/saved/i).first().waitFor();
  for (const [id, ext] of [['pdf', '.pdf'], ['xlsx', '.xlsx'], ['dxf', '.dxf']]) {
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.locator(`[data-ribbon="${id}"]`).click()]);
    await dl.saveAs(`${out}/export-column${ext}`);
    console.log('download', dl.suggestedFilename(), require('fs').statSync(`${out}/export-column${ext}`).size);
  }
  await page.getByText('Section', { exact: true }).first().click();
  await page.getByText('Checks', { exact: true }).first().click();
  await page.keyboard.press('Alt+t');
  await page.waitForTimeout(500);
  await shot('c2-column-light');
  await page.getByText('Charts', { exact: true }).first().click();
  await page.waitForTimeout(500);
  await shot('c3-column-charts-light');
  await page.keyboard.press('Alt+t');
  await page.waitForTimeout(300);

  // Slab, footings and continuous beam: the drawing tabs follow the element's views.
  for (const el of [
    { name: 'slab', link: /New RCC slab/, key: 'Two-way, Table 26 case 4', first: 'Plan', second: 'Section across the short span' },
    { name: 'footing', link: /New RCC isolated footing/, key: '2200 x 2050 x 450', first: 'Plan', second: 'Section along L' },
    { name: 'combined-footing', link: /New RCC combined footing/, key: '6100 x 1950 x 900', first: 'Plan', second: 'Section along the footing' },
    { name: 'continuous', link: /New RCC continuous beam/, key: '10-T12 (6+4)', first: 'Elevation: end span and half of span 2',
      second: 'Sections A-A and B-B' },
  ]) {
    step(el.name);
    await page.locator('[data-ribbon="project"]').click();
    await page.getByRole('link', { name: el.link }).click();
    await page.getByText(el.key).first().waitFor({ timeout: 15000 });
    await page.getByText(el.first, { exact: true }).first().waitFor({ timeout: 10000 });
    await page.waitForTimeout(500);
    await shot(`${el.name}-1-plan`);
    await page.keyboard.press('Control+s');
    await page.waitForURL('**/designs/*', { timeout: 10000 });
    await page.getByText(/saved/i).first().waitFor();
    for (const [id, ext] of [['pdf', '.pdf'], ['xlsx', '.xlsx'], ['dxf', '.dxf']]) {
      const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.locator(`[data-ribbon="${id}"]`).click()]);
      await dl.saveAs(`${out}/export-${el.name}${ext}`);
      console.log('download', dl.suggestedFilename(), require('fs').statSync(`${out}/export-${el.name}${ext}`).size);
    }
    await page.getByText(el.second, { exact: true }).first().click();
    await page.getByText('Bar schedule', { exact: true }).first().click();
    await page.waitForTimeout(500);
    await shot(`${el.name}-2-section-bbs`);
  }

  step('continuous beam by elastic analysis');
  await page.locator('[data-ribbon="project"]').click();
  await page.getByRole('link', { name: /New RCC continuous beam/ }).click();
  await page.getByLabel('Analysis', { exact: true }).waitFor({ timeout: 15000 });
  await page.getByLabel('Analysis', { exact: true }).selectOption('elastic');
  await page.getByLabel('Member mark').fill('CB2');
  await page.getByRole('table', { name: 'Spans' }).waitFor();
  await page.getByText('Span 1: support 1 to support 2', { exact: true }).first().waitFor({ timeout: 15000 });
  await page.getByLabel('Clear span, row 3').fill('5500');
  await page.getByRole('button', { name: 'Add row' }).first().click(); // a fourth span, copying the third
  // more views than drawing panels: each panel picks the one it shows, and its tab follows
  const picker = page.locator('select[id^="view-"]').first(); // the drawing tab in front (a saved layout may have either)
  await picker.locator('option', { hasText: 'Span 4: support 4 to support 5' }).waitFor({ state: 'attached', timeout: 15000 });
  await picker.selectOption({ label: 'Span 4: support 4 to support 5' });
  await page.getByText('Span 4: support 4 to support 5', { exact: true }).first().waitFor({ timeout: 10000 });
  await page.waitForTimeout(500);
  await shot('continuous-elastic-1-elevation');
  await page.getByText('Charts', { exact: true }).first().click();
  await page.waitForTimeout(600);
  await shot('continuous-elastic-2-charts');
  await page.keyboard.press('Control+s');
  await page.waitForURL('**/designs/*', { timeout: 10000 });
  await page.getByText(/saved/i).first().waitFor();
  for (const [id, ext] of [['pdf', '.pdf'], ['xlsx', '.xlsx'], ['dxf', '.dxf']]) {
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.locator(`[data-ribbon="${id}"]`).click()]);
    await dl.saveAs(`${out}/export-continuous-elastic${ext}`);
    console.log('download', dl.suggestedFilename(), require('fs').statSync(`${out}/export-continuous-elastic${ext}`).size);
  }
  await page.getByText('Bar schedule', { exact: true }).first().click();
  await page.waitForTimeout(500);
  await shot('continuous-elastic-3-bbs');

  step('export a project and import it again');
  await page.locator('[data-ribbon="project"]').click();
  await page.getByRole('button', { name: 'Export project' }).waitFor();
  const [archive] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.getByRole('button', { name: 'Export project' }).click()]);
  const archivePath = `${out}/export-project.clp.json`;
  await archive.saveAs(archivePath);
  const designsIn = JSON.parse(require('fs').readFileSync(archivePath, 'utf8')).designs.length;
  console.log('download', archive.suggestedFilename(), designsIn, 'designs');
  await page.goto(BASE + '/projects');
  await page.getByLabel('Project archive file').setInputFiles(archivePath);
  await page.getByText(/Imported as job number .*-2 /).first().waitFor({ timeout: 15000 });
  await page.waitForURL('**/projects/*');
  await page.waitForTimeout(500);
  await shot('15-imported-project');

  step('back up the database');
  await page.goto(BASE + '/admin/data');
  await page.getByRole('heading', { name: 'Data and backup' }).waitFor();
  const [db] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.getByRole('button', { name: 'Download a backup' }).click()]);
  await db.saveAs(`${out}/backup.db`);
  const head = require('fs').readFileSync(`${out}/backup.db`).subarray(0, 15).toString('latin1');
  if (head !== 'SQLite format 3') throw new Error('the backup is not a database: ' + head);
  console.log('download', db.suggestedFilename(), require('fs').statSync(`${out}/backup.db`).size);
  await shot('16-data-and-backup');

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
