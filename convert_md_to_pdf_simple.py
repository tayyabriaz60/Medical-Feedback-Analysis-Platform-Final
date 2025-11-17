#!/usr/bin/env python3

"""
Convert Markdown file to PDF (Simple Version - Works on Windows)

Usage: python3 convert_md_to_pdf_simple.py <input.md> [output.pdf]
"""

import sys
import os


def convert_md_to_pdf(md_file, pdf_file=None):
    """Convert markdown file to PDF using reportlab"""
    
    if pdf_file is None:
        pdf_file = md_file.replace('.md', '.pdf')
    
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
        from reportlab.lib import colors
        import markdown
        from html.parser import HTMLParser
        
        # Read markdown file
        print(f"[INFO] Reading markdown file: {md_file}")
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # Convert markdown to HTML
        print("[INFO] Converting markdown to HTML...")
        html_content = markdown.markdown(
            md_content,
            extensions=['tables', 'fenced_code', 'codehilite']
        )
        
        # Create PDF
        print(f"[INFO] Creating PDF: {pdf_file}")
        doc = SimpleDocTemplate(pdf_file, pagesize=A4, topMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Add custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            borderPadding=10,
            borderColor=colors.HexColor('#3498db'),
            borderWidth=2,
            borderBottom=2,
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=12,
            spaceBefore=12,
            borderPadding=5,
            borderColor=colors.HexColor('#95a5a6'),
            borderWidth=1,
            borderBottom=1,
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            spaceAfter=6,
        )
        
        code_style = ParagraphStyle(
            'CustomCode',
            parent=styles['Normal'],
            fontSize=8,
            fontName='Courier',
            textColor=colors.HexColor('#2c3e50'),
            backColor=colors.HexColor('#f4f4f4'),
            spaceAfter=6,
        )
        
        # Parse HTML and add to story
        lines = html_content.split('\n')
        for line in lines:
            line = line.strip()
            
            if line.startswith('<h1>'):
                text = line.replace('<h1>', '').replace('</h1>', '')
                story.append(Paragraph(text, title_style))
                story.append(Spacer(1, 0.2*inch))
                
            elif line.startswith('<h2>'):
                text = line.replace('<h2>', '').replace('</h2>', '')
                story.append(Paragraph(text, heading_style))
                story.append(Spacer(1, 0.1*inch))
                
            elif line.startswith('<h3>'):
                text = line.replace('<h3>', '').replace('</h3>', '')
                story.append(Paragraph(text, styles['Heading3']))
                story.append(Spacer(1, 0.05*inch))
                
            elif line.startswith('<p>'):
                text = line.replace('<p>', '').replace('</p>', '')
                text = text.replace('<strong>', '<b>').replace('</strong>', '</b>')
                text = text.replace('<em>', '<i>').replace('</em>', '</i>')
                if text.strip():
                    story.append(Paragraph(text, normal_style))
                    story.append(Spacer(1, 0.05*inch))
                
            elif line.startswith('<pre>'):
                text = line.replace('<pre>', '').replace('</pre>', '').replace('<code>', '').replace('</code>', '')
                if text.strip():
                    story.append(Paragraph(text, code_style))
                    story.append(Spacer(1, 0.1*inch))
                
            elif line.startswith('<code>'):
                text = line.replace('<code>', '').replace('</code>', '')
                if text.strip():
                    story.append(Paragraph(text, code_style))
                    story.append(Spacer(1, 0.05*inch))
                
            elif line == '<hr>':
                story.append(Spacer(1, 0.1*inch))
                
            elif line.startswith('<ul>') or line.startswith('<li>'):
                text = line.replace('<ul>', '').replace('</ul>', '').replace('<li>', '• ').replace('</li>', '')
                if text.strip():
                    story.append(Paragraph(text, normal_style))
        
        # Build PDF
        doc.build(story)
        
        print(f"\n[SUCCESS] Successfully converted '{md_file}' to '{pdf_file}'")
        print(f"[INFO] File size: {os.path.getsize(pdf_file) / 1024:.2f} KB")
        return True
        
    except ImportError as e:
        print(f"\n[ERROR] Missing required library: {e}")
        print("\n[INFO] Installing required packages...")
        print("Run: pip install reportlab markdown")
        return False
        
    except Exception as e:
        print(f"\n[ERROR] Error during conversion: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_md_to_pdf_simple.py <input.md> [output.pdf]")
        print("\nExample:")
        print("  python convert_md_to_pdf_simple.py DETAILED_WORKFLOW_REPORT.md")
        print("  python convert_md_to_pdf_simple.py DETAILED_WORKFLOW_REPORT.md report.pdf")
        sys.exit(1)
    
    md_file = sys.argv[1]
    pdf_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(md_file):
        print(f"❌ Error: File '{md_file}' not found!")
        sys.exit(1)
    
    convert_md_to_pdf(md_file, pdf_file)

