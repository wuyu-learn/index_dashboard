import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("data/data_result_fixed.xlsx");
const workbook = await SpreadsheetFile.importXlsx(input);
console.log((await workbook.inspect({ kind: "sheet", include: "id,name" })).ndjson);
console.log(
  (
    await workbook.inspect({
      kind: "table",
      range: "Sheet1!A1:G12",
      include: "values,formulas",
      tableMaxRows: 12,
      tableMaxCols: 7,
    })
  ).ndjson,
);
console.log(
  (
    await workbook.inspect({
      kind: "table",
      range: "Sheet1!A91:G94",
      include: "values,formulas",
      tableMaxRows: 4,
      tableMaxCols: 7,
    })
  ).ndjson,
);
console.log(
  (
    await workbook.inspect({
      kind: "table",
      range: "Sheet1!A399:G402",
      include: "values,formulas",
      tableMaxRows: 4,
      tableMaxCols: 7,
    })
  ).ndjson,
);
console.log(
  (
    await workbook.inspect({
      kind: "match",
      searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
      options: { useRegex: true, maxResults: 100 },
      summary: "formula error scan",
    })
  ).ndjson,
);
const preview = await workbook.render({
  sheetName: "Sheet1",
  range: "A1:G20",
  scale: 1.5,
});
await fs.writeFile(
  "data/metadata/data_result_fixed_preview.png",
  Buffer.from(await preview.arrayBuffer()),
);
