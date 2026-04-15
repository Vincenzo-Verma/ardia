import fs from "fs";
import path from "path";
import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  AlignmentType,
  Header,
  Footer,
  PageNumber,
  convertInchesToTwip,
} from "docx";

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  console.error("Usage: node generate.js <input.json> <output.docx>");
  process.exit(1);
}

const draft = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const generationDate = new Date().toLocaleDateString("en-US", {
  year: "numeric",
  month: "long",
  day: "numeric",
});

function heading1(text, color = "1F4E8B") {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [
      new TextRun({
        text,
        font: "Arial",
        color,
        bold: true,
      }),
    ],
    spacing: { before: 240, after: 120 },
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [
      new TextRun({
        text,
        font: "Arial",
        bold: true,
      }),
    ],
    spacing: { before: 200, after: 80 },
  });
}

function bodyParagraph(text) {
  return new Paragraph({
    children: [
      new TextRun({
        text,
        font: "Arial",
        size: 22,
      }),
    ],
    spacing: { before: 80, after: 80 },
  });
}

function numberedParagraph(index, text) {
  return new Paragraph({
    children: [
      new TextRun({
        text: `${index}. ${text}`,
        font: "Arial",
        size: 20,
      }),
    ],
    spacing: { before: 40, after: 40 },
  });
}

const children = [];

children.push(heading1(draft.title));

for (const section of draft.sections) {
  children.push(heading2(section.heading));
  for (const line of section.body.split("\n")) {
    if (line.trim()) {
      children.push(bodyParagraph(line.trim()));
    }
  }
}

children.push(heading1("Bibliography"));
draft.bibliography.forEach((url, i) => {
  children.push(numberedParagraph(i + 1, url));
});

const doc = new Document({
  sections: [
    {
      properties: {
        page: {
          size: {
            width: 12240,
            height: 15840,
          },
          margin: {
            top: convertInchesToTwip(1),
            bottom: convertInchesToTwip(1),
            left: convertInchesToTwip(1),
            right: convertInchesToTwip(1),
          },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              children: [
                new TextRun({
                  text: draft.title,
                  font: "Arial",
                  size: 18,
                }),
                new TextRun({
                  text: `\t${generationDate}`,
                  font: "Arial",
                  size: 18,
                }),
              ],
              alignment: AlignmentType.LEFT,
              tabStops: [
                {
                  type: "right",
                  position: convertInchesToTwip(6.5),
                },
              ],
            }),
          ],
        }),
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({
                  children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES],
                  font: "Arial",
                  size: 18,
                }),
              ],
            }),
          ],
        }),
      },
      children,
    },
  ],
});

Packer.toBuffer(doc)
  .then((buffer) => {
    fs.writeFileSync(outputPath, buffer);
    process.exit(0);
  })
  .catch((err) => {
    console.error("Failed to generate DOCX:", err);
    process.exit(1);
  });
