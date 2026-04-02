import os
import json
from typing import Dict, List, Union
import glob
import re
from .schemas import ReferenceItem

def extract_steps(base_dir: str, output_dir: str):
    """
    Extracts step descriptions from the experiment's step folder and saves them
    to a steps.txt file in the specified output directory.
    """
    step_descriptions = []
    
    if not os.path.isdir(base_dir):
        return
        
    # Iterate through step folders
    for step_dir in sorted(os.listdir(base_dir)):
        dir_path = os.path.join(base_dir, step_dir)
        if os.path.isdir(dir_path):
            events_file = os.path.join(dir_path, 'events.jsonl')
            if os.path.exists(events_file):
                with open(events_file, 'r', encoding='utf-8') as f:
                    first_line = f.readline()
                    if first_line:
                        try:
                            data = json.loads(first_line)
                            description = data.get('payload', {}).get('description', '')
                            if description:
                                step_descriptions.append(f"Step {step_dir}: {description}")
                        except json.JSONDecodeError:
                            print(f"Error decoding JSON in {events_file}")
                            
    # Write to output file in the output directory
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "steps.txt")
    with open(output_file, 'w', encoding='utf-8') as f:
        for desc in step_descriptions:
            f.write(desc + '\n')

def assemble_latex_document(draft_sections: Union[Dict[str, str], str], abstract: str, title: str, references: List[ReferenceItem] = None) -> str:
    """Agent responsible for assembling the final LaTeX document."""
    print("Executing Assembly Agent...")
    
    # Create the preamble
    latex_doc = f"""\\documentclass[conference]{{IEEEtran}}
\\usepackage{{cite}}
\\usepackage{{amsmath,amssymb,amsfonts}}
\\usepackage{{graphicx}}
\\usepackage{{textcomp}}
\\usepackage{{xcolor}}
\\usepackage{{booktabs}}
\\usepackage{{hyperref}}
\\usepackage{{titlesec}}

% Customize section headings to be left-aligned, bold, and use Arabic numerals
\\titleformat{{\\section}}
  {{\\normalfont\\Large\\bfseries}}
  {{\\arabic{{section}}.}}
  {{1em}}
  {{}}
\\titleformat{{\\subsection}}
  {{\\normalfont\\large\\bfseries}}
  {{\\arabic{{section}}.\\arabic{{subsection}}}}
  {{1em}}
  {{}}
\\titleformat{{\\subsubsection}}
  {{\\normalfont\\normalsize\\bfseries}}
  {{\\arabic{{section}}.\\arabic{{subsection}}.\\arabic{{subsubsection}}}}
  {{1em}}
  {{}}

\\begin{{document}}

\\title{{{title}}}

\\author{{\\IEEEauthorblockN{{Writing Agent System}}}}

\\maketitle

\\begin{{center}}
\\textbf{{\\Large Abstract}}
\\end{{center}}
{abstract}

\\vspace{{1em}}

"""
    
    # Append sections
    if isinstance(draft_sections, dict):
        for section_title, content in draft_sections.items():
            if section_title.lower() != "abstract":
                # Ensure we only have one \section{...} for this section title.
                # Since the content might already contain \section{Title}, we strip it out
                # and explicitly add our own to ensure consistent formatting.
                pattern = r'^\s*\\section\*?\{[^\}]+\}\s*'
                clean_content = re.sub(pattern, '', content, count=1, flags=re.IGNORECASE | re.MULTILINE)
                latex_doc += f"\n\\section{{{section_title}}}\n{clean_content.strip()}\n\n"
    elif isinstance(draft_sections, str):
        # If a single pre-assembled string (e.g., from revision agent) is passed
        content = draft_sections
        # Strip out any hallucinated abstract blocks
        content = re.sub(r'\\section\*?\{Abstract\}.*?(?=\\section)', '', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'\\begin\{abstract\}.*?\\end\{abstract\}', '', content, flags=re.IGNORECASE | re.DOTALL)
        latex_doc += f"\n{content.strip()}\n\n"
            
    if references and len(references) > 0:
        latex_doc += "\n\\bibliographystyle{IEEEtran}\n\\bibliography{references}\n"
        
    latex_doc += "\\end{document}"
    
    return latex_doc

def load_context_files(exp_dir: str, output_dir: str = None) -> Dict[str, str]:
    """
    Loads the necessary markdown and text files for context dynamically from the given experiment directory.
    - Reads all .md files in exp_dir/src/
    - Reads steps.txt in exp_dir/step/
    - Loads all .png paths in exp_dir/src/sandbox/
    - Extracts the research plan from a prompt_attempt_1.md file
    """
    context = {}
    md_titles = {} # Dictionary to map filename to its extracted H1 title
    
    src_dir = os.path.join(exp_dir, "src")
    if os.path.isdir(src_dir):
        md_files = glob.glob(os.path.join(src_dir, "*.md"))
        for report_path in md_files:
            filename = os.path.basename(report_path)
            with open(report_path, "r", encoding="utf-8") as f:
                content = f.read()
                
                # Extract the first H1 heading (e.g., "# Title") to use as the document's main title
                match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                if match:
                    title = match.group(1).strip()
                    context[filename] = content
                    md_titles[filename] = title
                else:
                    print(f"Warning: Skipping '{filename}' as it does not contain an H1 heading (# Title).")
                    
    # We can pass the extracted titles along by storing them in a special hidden key
    import json
    context["__md_titles__"] = json.dumps(md_titles)
                
    # Load steps.txt from the output directory (where it was extracted)
    if output_dir:
        steps_file = os.path.join(output_dir, "steps.txt")
        if os.path.exists(steps_file):
            with open(steps_file, "r", encoding="utf-8") as f:
                context["steps.txt"] = f.read()
            
    # Load available PNG files from the sandbox directory
    sandbox_dir = os.path.join(src_dir, "sandbox")
    if os.path.isdir(sandbox_dir):
        png_files = glob.glob(os.path.join(sandbox_dir, "*.png"))
        for png_path in png_files:
            filename = os.path.basename(png_path)
            context[filename] = png_path
            
    # Extract research idea from prompt_attempt_1.md
    step_dir = os.path.join(exp_dir, "step")
    if os.path.isdir(step_dir):
        prompt_files = glob.glob(os.path.join(step_dir, "**", "prompt_attempt_1.md"), recursive=True)
        if prompt_files:
            with open(prompt_files[0], "r", encoding="utf-8") as f:
                content = f.read()
                
            match = re.search(r'\*\*Research idea \(project context\):\*\*(.*?)\*\*Input description:\*\*', content, re.DOTALL)
            if match:
                research_plan = match.group(1).strip()
                
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                    research_plan_path = os.path.join(output_dir, "research_plan.md")
                    with open(research_plan_path, "w", encoding="utf-8") as rf:
                        rf.write(research_plan)
                
                context["research_plan.md"] = research_plan
        
    return context
