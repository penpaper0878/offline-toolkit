// End-to-end walkthrough in a real browser: register, create a project, design a beam, a column, a slab,
// isolated, combined and strap footings, a continuous beam (by coefficients and by elastic analysis), save, import a schedule of rates,
// write a rate analysis and an estimate (measured and design quantities), export and import a project, back up the database, download each report / schedule / drawing, switch theme, search, use the calculator,
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
  await page.getByRole('option', { name: /beam B1/i }).waitFor({ timeout: 8000 });
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
    { name: 'strap-footing', link: /New RCC strap footing/, key: '1600 x 3200 x 700', first: 'Plan', second: 'Section along the strap' },
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

  step('quantity estimation: a schedule of rates, a rate analysis and an estimate');
  const fs = require('fs');
  const designUrl = page.url();
  const sorPath = `${out}/illustrative-sor.csv`;
  fs.writeFileSync(sorPath, [
    'Illustrative schedule of rates: made up for this walkthrough, not an official schedule',
    'Code,Description,Unit,Rate',
    ',Chapter 2: Earth work,,',
    '2.6,"Earth work in excavation by mechanical means over areas, in all kinds of soil, disposal up to 50 m lead and 1.5 m lift",cum,212.40',
    ',Chapter 5: Concrete work,,',
    '5.1,"Providing and laying in position cement concrete of specified grade, excluding centering and shuttering, up to plinth level",,',
    '5.1.2,M20 grade,cum,"7,240.00"',
    '5.9,Centering and shuttering including strutting and removal of form for foundations and footings,sqm,318.60',
    '5.22,"Steel reinforcement for R.C.C. work including straightening, cutting, bending, placing in position and binding",kg,96.75',
  ].join('\n') + '\n');
  await page.keyboard.press('Alt+4');
  await page.getByRole('heading', { name: 'Quantity estimation' }).waitFor();
  await page.getByRole('button', { name: 'Import a schedule' }).click();
  const imp = page.getByRole('dialog', { name: 'Import a schedule of rates' });
  await imp.getByLabel('Title').fill('Illustrative schedule 2026');
  await imp.getByLabel('Authority').fill('Illustrative');
  await imp.getByLabel('State').fill('Gujarat');
  await imp.getByLabel('Year').fill('2026');
  await page.getByLabel('Schedule of rates file').setInputFiles(sorPath);
  await imp.getByRole('button', { name: 'Import', exact: true }).click();
  await imp.getByText(/4 items imported/).waitFor({ timeout: 10000 });
  await shot('e1-schedule-imported');
  await imp.getByRole('button', { name: 'Done' }).click();

  await page.getByRole('button', { name: 'New rate analysis' }).click();
  const ra = page.getByRole('dialog', { name: 'New rate analysis' });
  await ra.getByRole('textbox', { name: 'Item', exact: true }).fill('Plain cement concrete 1:4:8 (illustrative)');
  await ra.getByRole('textbox', { name: 'Unit', exact: true }).fill('cum');
  await ra.getByLabel('Description, line 1').fill('Cement');
  await ra.getByLabel('Quantity, line 1').fill('3.4');
  await ra.getByLabel('Rate, line 1').fill('410');
  await ra.getByRole('button', { name: 'Add line' }).click();
  await ra.getByRole('combobox').nth(1).click();
  await page.getByRole('option', { name: 'Labour' }).click();
  await ra.getByLabel('Description, line 2').fill('Mason and labour, per cum');
  await ra.getByLabel('Quantity, line 2').fill('1');
  await ra.getByLabel('Rate, line 2').fill('1250');
  await ra.getByText('Rate per cum').waitFor({ timeout: 10000 });
  await shot('e2-rate-analysis');
  await ra.getByRole('button', { name: 'Save' }).click();
  await page.getByRole('button', { name: 'Plain cement concrete 1:4:8 (illustrative)', exact: true }).waitFor();

  await page.getByRole('button', { name: 'New estimate' }).click();
  const ne = page.getByRole('dialog', { name: 'New estimate' });
  await ne.getByLabel('Project').click();
  await page.getByRole('option', { name: /Ward 12 Community Hall/ }).first().click();
  await ne.getByLabel('Estimate title').fill('Foundations');
  await ne.getByRole('button', { name: 'Create' }).click();
  await page.waitForURL('**/estimates/*');
  await page.getByRole('heading', { name: 'Foundations' }).waitFor();

  await page.getByRole('button', { name: 'Add item' }).click();
  await page.getByRole('menuitem', { name: 'From a schedule of rates' }).click();
  const pick = page.getByRole('dialog', { name: 'Add an item from a schedule of rates' });
  await pick.getByLabel('Search by code or words').fill('M20');
  await pick.getByRole('button', { name: 'Add item 5.1.2' }).click();
  await pick.getByLabel('Search by code or words').fill('reinforcement');
  await pick.getByRole('button', { name: 'Add item 5.22' }).click();
  await pick.getByRole('button', { name: 'Close' }).click();
  await page.getByRole('button', { name: 'Add a measurement line, item 1' }).click();
  await page.getByLabel('Measurement, item 1 line 1').fill('Footings F1 to F4');
  await page.getByLabel('Nos, item 1 line 1').fill('4');
  await page.getByLabel('Length, item 1 line 1').fill('1.8');
  await page.getByLabel('Breadth, item 1 line 1').fill('1.8');
  await page.getByLabel('Depth, item 1 line 1').fill('0.45');
  await page.getByRole('cell', { name: '5.83' }).first().waitFor({ timeout: 10000 });
  await page.getByLabel('Quantity from, item 2').selectOption('design');
  const designQty = page.getByLabel('Design quantity, item 2');
  const steel = await designQty.locator('option', { hasText: 'reinforcement steel' }).first().getAttribute('value');
  await designQty.selectOption(steel);
  await page.getByText(/recorded with its revision when the estimate is saved/).waitFor({ timeout: 10000 });
  await page.getByRole('button', { name: 'Add a percentage addition' }).click();
  await page.getByLabel('Label, addition 1').fill('Contingencies');
  await page.getByLabel('Percentage, addition 1').fill('3');
  await page.waitForTimeout(800);
  await page.keyboard.press('Control+s');
  await page.getByText('Estimate saved').first().waitFor({ timeout: 10000 });
  await page.getByText(/taken at R\d+: /).first().waitFor({ timeout: 10000 });
  await page.waitForTimeout(500);
  await shot('e3-estimate');
  for (const [label, ext] of [['Excel', 'xlsx'], ['PDF', 'pdf']]) {
    const [file] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.getByRole('button', { name: label, exact: true }).click()]);
    await file.saveAs(`${out}/estimate.${ext}`);
    const magic = fs.readFileSync(`${out}/estimate.${ext}`).subarray(0, 4).toString('latin1');
    if (magic !== (ext === 'pdf' ? '%PDF' : 'PK\u0003\u0004')) throw new Error(`the ${label} estimate is not a ${ext} file`);
    console.log('download', file.suggestedFilename(), fs.statSync(`${out}/estimate.${ext}`).size);
  }
  await page.goto(designUrl);
  await page.locator('[data-ribbon="project"]').waitFor({ timeout: 15000 });

  step('export a project and import it again');
  await page.locator('[data-ribbon="project"]').click();
  await page.getByRole('button', { name: 'Export project' }).waitFor();
  const [archive] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.getByRole('button', { name: 'Export project' }).click()]);
  const archivePath = `${out}/export-project.clp.json`;
  await archive.saveAs(archivePath);
  const archived = JSON.parse(require('fs').readFileSync(archivePath, 'utf8'));
  console.log('download', archive.suggestedFilename(), archived.designs.length, 'designs', archived.estimates.length, 'estimates');
  if (archived.estimates.length !== 1) throw new Error('the archive does not carry the estimate');
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
  await page.getByRole('alert').filter({ hasText: 'Backup saved' }).waitFor({ state: 'hidden', timeout: 10000 }); // not over the dashboard

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
