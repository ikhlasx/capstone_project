"""Convert Markdown Capstone Technical Report into a professional Word (.docx) document."""
from __future__ import annotations

import re
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

NAVY_PRIMARY = RGBColor(0x1A, 0x36, 0x5D)
BLUE_SECONDARY = RGBColor(0x2B, 0x6C, 0xB0)
CHARCOAL_DARK = RGBColor(0x2D, 0x37, 0x48)
MUTED_GRAY = RGBColor(0x71, 0x80, 0x96)


def add_inline_formatted(paragraph, text: str):
    """Parse bold, italic, code, and math spans and add them with proper formatting."""
    # Pattern to match **bold**, *italic*, `code`, and $math$
    tokens = re.split(r'(\*\*.*?\*\*|\*.*?\*|`.*?`|\$.*?\$)', text)
    for token in tokens:
        if not token:
            continue
        if token.startswith('**') and token.endswith('**') and len(token) >= 4:
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith('*') and token.endswith('*') and len(token) >= 2:
            run = paragraph.add_run(token[1:-1])
            run.italic = True
        elif token.startswith('`') and token.endswith('`') and len(token) >= 2:
            run = paragraph.add_run(token[1:-1])
            run.font.name = 'Consolas'
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(0xC5, 0x30, 0x30)
        elif token.startswith('$') and token.endswith('$') and len(token) >= 2:
            run = paragraph.add_run(token[1:-1])
            run.italic = True
        else:
            paragraph.add_run(token)


def style_table(table):
    """Apply elegant professional formatting to a docx table."""
    table.autofit = False
    
    # Header row shading & bolding
    header_tr = table.rows[0]
    for cell in header_tr.cells:
        shading = parse_xml(r'<w:shd {} w:fill="2B6CB0"/>'.format(nsdecls('w')))
        cell._tc.get_or_add_tcPr().append(shading)
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            for run in p.runs:
                run.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(9.5)
                
    # Data rows alternating shading
    for r_idx, row in enumerate(table.rows[1:], start=1):
        bg_color = "F7FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for cell in row.cells:
            if bg_color != "FFFFFF":
                shading = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls('w'), bg_color))
                cell._tc.get_or_add_tcPr().append(shading)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(3)
                p.paragraph_format.space_after = Pt(3)
                for run in p.runs:
                    run.font.size = Pt(9)


def markdown_to_docx(md_path: Path, docx_path: Path):
    doc = docx.Document()
    
    # Page setup: Standard Margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Base styles
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = CHARCOAL_DARK

    lines = md_path.read_text(encoding='utf-8').splitlines()
    i = 0
    in_table = False
    table_lines: list[str] = []

    def flush_table():
        nonlocal in_table, table_lines
        if not table_lines:
            return
        # Parse rows
        parsed_rows = []
        for line in table_lines:
            stripped = line.strip().strip('|')
            if re.match(r'^[\s\-\|\:]+$', stripped):
                continue # delimiter row
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if cells:
                parsed_rows.append(cells)
                
        if parsed_rows:
            num_cols = max(len(r) for r in parsed_rows)
            t = doc.add_table(rows=len(parsed_rows), cols=num_cols)
            t.style = 'Table Grid'
            for r_idx, row in enumerate(parsed_rows):
                for c_idx, cell_text in enumerate(row):
                    if c_idx < num_cols:
                        cell = t.rows[r_idx].cells[c_idx]
                        p = cell.paragraphs[0]
                        p.text = ''
                        add_inline_formatted(p, cell_text)
            style_table(t)
            # Add small spacing after table
            p_after = doc.add_paragraph()
            p_after.paragraph_format.space_before = Pt(2)
            p_after.paragraph_format.space_after = Pt(4)
        table_lines = []
        in_table = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Table detection
        if stripped.startswith('|') and stripped.endswith('|'):
            in_table = True
            table_lines.append(stripped)
            i += 1
            continue
        elif in_table:
            flush_table()

        # Blank line
        if not stripped:
            i += 1
            continue

        # Horizontal divider
        if stripped == '---':
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run('_______________________________________________________________________________')
            run.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE0)
            run.font.size = Pt(8)
            i += 1
            continue

        # Title
        if stripped.startswith('# '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(stripped[2:])
            run.bold = True
            run.font.size = Pt(22)
            run.font.color.rgb = NAVY_PRIMARY
            i += 1
            continue

        # Subtitle
        if stripped.startswith('## '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(stripped[3:])
            run.bold = True
            run.font.size = Pt(14)
            run.font.color.rgb = BLUE_SECONDARY
            i += 1
            continue

        # Heading 3
        if stripped.startswith('### '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(stripped[4:])
            run.bold = True
            run.font.size = Pt(12)
            run.font.color.rgb = CHARCOAL_DARK
            i += 1
            continue

        # Heading 4
        if stripped.startswith('#### '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(stripped[5:])
            run.bold = True
            run.font.size = Pt(11)
            run.font.color.rgb = CHARCOAL_DARK
            i += 1
            continue

        # Blockquote / Note
        if stripped.startswith('> '):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.4)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(stripped[2:])
            run.italic = True
            run.font.color.rgb = MUTED_GRAY
            i += 1
            continue

        # Bullet lists
        if stripped.startswith(('- ', '* ')):
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            add_inline_formatted(p, stripped[2:])
            i += 1
            continue

        # Numbered lists (e.g. 1. , 2. )
        m_num = re.match(r'^(\d+)\.\s+(.*)$', stripped)
        if m_num:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            run_num = p.add_run(f"{m_num.group(1)}. ")
            run_num.bold = True
            add_inline_formatted(p, m_num.group(2))
            i += 1
            continue

        # Regular paragraph
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        add_inline_formatted(p, stripped)
        i += 1

    if in_table:
        flush_table()

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    print(f"Successfully generated: {docx_path}")


if __name__ == '__main__':
    md_in = Path("E:/iit roorke/FDE_Capstone_Complete/IkhlasPV_Capstone_Report_Draft.md")
    docx_out = Path("E:/iit roorke/FDE_Capstone_Complete/IkhlasPV_Capstone_Report.docx")
    markdown_to_docx(md_in, docx_out)

