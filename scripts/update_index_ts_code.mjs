import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.cwd();
const workbookPath = path.join(root, "data", "data_result_fixed.xlsx");
const backupPath = path.join(root, "data", "data_result_fixed.before_ts_code.xlsx");
const mappingPath = path.join(
  root,
  "data",
  "metadata",
  "index_basic_mapping.json",
);

const mapping = JSON.parse(await fs.readFile(mappingPath, "utf8"));
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Sheet1");

if (mapping.length !== 483) {
  throw new Error(`Expected 483 mapping rows, received ${mapping.length}`);
}

const existing = await workbook.inspect({
  kind: "table",
  range: "Sheet1!A1:G484",
  include: "values",
  tableMaxRows: 2,
  tableMaxCols: 7,
});
if (existing.ndjson.includes('"ts_code"')) {
  throw new Error("Workbook already contains a ts_code column");
}

sheet.getRange("G1:G484").copyFrom(sheet.getRange("F1:F484"), "all");
sheet.getRange("G1:G484").values = [
  ["ts_code"],
  ...mapping.map((row) => [row.ts_code ?? null]),
];

await fs.copyFile(workbookPath, backupPath);
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(workbookPath);

console.log(`updated: ${workbookPath}`);
console.log(`backup: ${backupPath}`);
