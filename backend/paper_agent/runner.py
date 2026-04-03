import os
import json
import asyncio
import shutil
from loguru import logger
from pathlib import Path

from .writing_agent import WritingAgent
from .utils import load_context_files, extract_steps, assemble_latex_document
from .config import BASE_DIR

async def run_paper_agent(
    experiment_id: str,
    api_config: dict,
    on_thinking=None,
    abort_event=None,
) -> dict:
    """
    Run Paper Agent based on 'mode'.
    Both 'llm' and 'agent' modes will use the full multi-stage WritingAgent pipeline.
    Expects input from sandbox/{experiment_id}/ and outputs to output/{experiment_id}/
    """
    mode = "mock" if api_config.get("paperUseMock", True) else "agent"
    logger.info(f"PaperAgent starting for {experiment_id} in mode={mode}")
    try:
        if on_thinking:
            await on_thinking("Initializing Paper Agent...\n", None, "Paper", None)

        if mode == "mock":
            if on_thinking:
                await on_thinking("Reading artifact outline...\n", None, "Paper", None)
            await asyncio.sleep(1.0)
            if on_thinking:
                await on_thinking("Drafting section: Introduction...\n", None, "Paper", None)
            await asyncio.sleep(1.5)
            
            final_markdown = f"""# Final Research Paper (Mock)
            
*Generated on the fly based on extracted tasks.*

## 1. Introduction
This is a mock introduction.
"""
            if on_thinking:
                await on_thinking("Draft complete.\n", None, "Paper", None)
            return {"content": final_markdown, "pdf_url": ""}

        # Mode: llm or agent (both use the new pipeline)
        # The pipeline relies on the sandbox directory structure
        src_dir = os.path.join(BASE_DIR, "sandbox", experiment_id)
        output_dir = os.path.join(BASE_DIR, "output", experiment_id)
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Extracting steps from {os.path.join(src_dir, 'step')}...")
        if on_thinking:
            await on_thinking(f"Extracting steps from {os.path.join(src_dir, 'step')}...\n", None, "Paper", None)
            
        step_dir = os.path.join(src_dir, "step")
        if os.path.exists(step_dir):
            await asyncio.to_thread(extract_steps, step_dir, output_dir)
            
        logger.info(f"Loading context files from {src_dir}...")
        if on_thinking:
            await on_thinking(f"Loading context files from {src_dir}...\n", None, "Paper", None)
        context = await asyncio.to_thread(load_context_files, src_dir, output_dir=output_dir)
        if not context:
            raise ValueError(f"No context files found in {src_dir}. Ensure the Task Agent has generated artifacts.")
            
        agent = WritingAgent(api_config)
        
        # 2. Stage 1: Planning
        if on_thinking:
            await on_thinking("Planning paper outline...\n", None, "PaperPlan", None)
        outline = await agent.generate_paper_outline(context)
        logger.info(f"Proposed Title: {outline.title}")
        logger.info(f"Generated {len(outline.sections)} sections in the outline.")
        if on_thinking:
            await on_thinking(f"\nProposed Title: {outline.title}\nGenerated {len(outline.sections)} sections in the outline.\n", None, "PaperPlan", None)
        
        # Save outline for reference
        with open(os.path.join(output_dir, "outline.json"), "w", encoding="utf-8") as f:
            f.write(outline.model_dump_json(indent=2))

        references_info = ""
        if hasattr(outline, 'references') and outline.references:
            references_info = "\\n".join([f"- {ref.citation_key}: {ref.bibtex_entry}" for ref in outline.references])
            
            # Save references.bib
            bib_path = os.path.join(output_dir, "references.bib")
            with open(bib_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join([ref.bibtex_entry for ref in outline.references]))
                
        # Copy assigned images to output directory
        logger.info("Copying assigned images to output directory...")
        if on_thinking:
            await on_thinking("Copying assigned images to output directory...\n", None, "PaperPlan", None)
        for section in outline.sections:
            for img_name in getattr(section, 'images', []):
                if img_name in context:
                    img_path = context[img_name]
                    dest_path = os.path.join(output_dir, img_name)
                    try:
                        shutil.copy2(img_path, dest_path)
                        logger.info(f"Copied {img_name} to output folder.")
                    except Exception as e:
                        logger.error(f"Error copying {img_name}: {e}")

        # 3. Stage 2: Drafting
        draft_sections = {}
        previously_drafted_text = ""
        for section in outline.sections:
            if on_thinking:
                await on_thinking(f"Drafting section: {section.title}...\n", None, "PaperWrite", None)
            draft_content = await agent.draft_section(
                section, 
                context, 
                references_info=references_info,
                full_outline=outline,
                previously_drafted_text=previously_drafted_text
            )
            
            import re
            if not re.search(r'\\section\*?\{', draft_content[:500], re.IGNORECASE):
                draft_content = f"\\section{{{section.title}}}\n" + draft_content
                
            draft_sections[section.title] = draft_content.strip()
            previously_drafted_text += f"\\n{draft_sections[section.title]}\\n"
            
        current_draft = ""
        for title, content in draft_sections.items():
            current_draft += f"\\n{content}\\n"
            
        # Optional Stage: Reference Enrichment
        logger.info("\nExecuting Reference Enrichment...")
        if on_thinking:
            await on_thinking("Enriching bibliographical references via Google Search...\n", None, "PaperWrite", None)
        enriched_result = await agent.enrich_references(current_draft, references_info)
        current_draft = enriched_result.updated_draft
        
        if enriched_result.new_references:
            logger.info(f"Added {len(enriched_result.new_references)} new references.")
            if on_thinking:
                await on_thinking(f"Added {len(enriched_result.new_references)} new references.\n", None, "PaperWrite", None)
            if not hasattr(outline, 'references') or outline.references is None:
                outline.references = []
            outline.references.extend(enriched_result.new_references)
            references_info = "\\n".join([f"- {ref.citation_key}: {ref.bibtex_entry}" for ref in outline.references])
            
            # Update references.bib file with new references
            bib_path = os.path.join(output_dir, "references.bib")
            with open(bib_path, "a", encoding="utf-8") as f:
                for ref in enriched_result.new_references:
                    f.write(f"\n\n{ref.bibtex_entry}")
                    
        # 4. Stage 3: Review and Revision Loop
        max_revisions = 3
        revision_count = 0
        is_approved = False
        approved_sections = []
        
        while revision_count < max_revisions and not is_approved:
            logger.info(f"\n--- Review Iteration {revision_count + 1} ---")
            if on_thinking:
                await on_thinking(f"\n--- Review Iteration {revision_count + 1} ---\nReviewing draft (Iteration {revision_count + 1}/{max_revisions})...\n", None, "PaperReview", None)
            review_result = await agent.review_draft(current_draft, outline, approved_sections=approved_sections)
            
            # Save review for reference
            with open(os.path.join(output_dir, f"review_iter_{revision_count + 1}.json"), "w", encoding="utf-8") as f:
                f.write(review_result.model_dump_json(indent=2))
                
            is_approved = review_result.is_approved
            
            if is_approved:
                logger.info("\nDraft Approved by Review Agent!")
                if on_thinking:
                    await on_thinking("\nDraft Approved by Review Agent!\n", None, "PaperReview", None)
                break
            else:
                logger.info("\nDraft needs revisions.")
                logger.info(f"Overall Feedback: {review_result.feedback}")
                logger.info("Executing Revision Agent to correct specific sections...")
                if on_thinking:
                    await on_thinking(f"\nDraft needs revisions.\nOverall Feedback: {review_result.feedback}\nExecuting Revision Agent to correct specific sections...\n", None, "PaperRevise", None)
                    
                flagged_sections = [r.section_title for r in review_result.required_revisions]
                for sec in outline.sections:
                    if sec.title not in flagged_sections and sec.title not in approved_sections:
                        approved_sections.append(sec.title)
                        logger.info(f"Section '{sec.title}' passed review and is now locked.")
                        if on_thinking:
                            await on_thinking(f"Section '{sec.title}' passed review and is now locked.\n", None, "PaperRevise", None)

                for revision in review_result.required_revisions:
                    sec_title = revision.section_title
                    sec_feedback = revision.feedback
                    
                    if sec_title in draft_sections:
                        sec_outline = next((s for s in outline.sections if s.title == sec_title), None)
                        if sec_outline:
                            sec_context = ""
                            for filename in sec_outline.required_context:
                                if filename in context:
                                    sec_context += f"\\n--- {filename} ---\\n{context[filename]}\\n"
                            
                            revised_section = await agent.revise_section(
                                section_title=sec_title,
                                current_section_draft=draft_sections[sec_title],
                                section_feedback=sec_feedback,
                                section_context=sec_context
                            )
                            
                            if not re.search(r'\\section\*?\{', revised_section[:500], re.IGNORECASE):
                                revised_section = f"\\section{{{sec_title}}}\n" + revised_section
                                
                            draft_sections[sec_title] = revised_section.strip()
                
                current_draft = ""
                for title, content in draft_sections.items():
                    current_draft += f"\\n{content}\\n"
                    
                revision_count += 1

        if not is_approved:
            logger.warning(f"\nWarning: Maximum revision iterations ({max_revisions}) reached. Proceeding to assembly with the current draft.")
            if on_thinking:
                await on_thinking(f"\nWarning: Maximum revision iterations ({max_revisions}) reached. Proceeding to assembly with the current draft.\n", None, "PaperRevise", None)

        # 5. Stage 4: Abstract Generation
        logger.info("\nGenerating Abstract based on final draft...")
        if on_thinking:
            await on_thinking("\nGenerating Abstract based on final draft...\nGenerating final abstract...\n", None, "PaperAssemble", None)
        abstract_text = await agent.generate_abstract(current_draft, outline.title)
            
        # 6. Stage 5: Assembly
        if on_thinking:
            await on_thinking("Assembling final document...\n", None, "PaperAssemble", None)
        
        final_latex = await asyncio.to_thread(
            assemble_latex_document, 
            current_draft, abstract_text, outline.title, getattr(outline, 'references', None)
        )
        
        latex_path = os.path.join(output_dir, "main.tex")
        with open(latex_path, "w", encoding="utf-8") as f:
            f.write(final_latex)
            
        # 7. Stage 6: Compilation and Fix Loop
        logger.info("\nAttempting to compile the final LaTeX document with tectonic...")
        if on_thinking:
            await on_thinking("\nAttempting to compile the final LaTeX document with tectonic...\n", None, "PaperCompile", None)
            
        max_compile_attempts = 3
        compile_attempt = 0
        compiled_successfully = False
        pdf_url = ""
        
        while compile_attempt < max_compile_attempts and not compiled_successfully:
            logger.info(f"Compilation Attempt {compile_attempt + 1}/{max_compile_attempts}...")
            if on_thinking:
                await on_thinking(f"Compilation Attempt {compile_attempt + 1}/{max_compile_attempts}...\n", None, "PaperCompile", None)
                
            try:
                proc = await asyncio.create_subprocess_exec(
                    "tectonic", "main.tex",
                    cwd=output_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
                
                if proc.returncode == 0:
                    logger.info("LaTeX compilation successful!")
                    if on_thinking:
                        await on_thinking("LaTeX compilation successful!\n", None, "PaperCompile", None)
                    compiled_successfully = True
                    pdf_url = f"/api/paper/pdf/{experiment_id}"
                else:
                    logger.info(f"Compilation failed with return code {proc.returncode}.")
                    error_log = stderr.decode('utf-8') if stderr else stdout.decode('utf-8')
                    if on_thinking:
                        await on_thinking(f"Compilation failed with return code {proc.returncode}. Error log snippet:\n{error_log[:500]}...\n", None, "PaperCompile", None)
                        
                    with open(os.path.join(output_dir, f"compile_error_{compile_attempt + 1}.log"), "w", encoding="utf-8") as f:
                        f.write(error_log)
                        
                    if compile_attempt < max_compile_attempts - 1:
                        logger.info("Invoking LaTeX Fixer Agent to resolve errors...")
                        if on_thinking:
                            await on_thinking("Invoking LaTeX Fixer Agent to resolve errors...\n", None, "PaperCompile", None)
                        
                        with open(latex_path, "r", encoding="utf-8") as f:
                            current_source = f.read()
                            
                        fixed_source = await agent.fix_latex_errors(current_source, error_log)
                        
                        with open(latex_path, "w", encoding="utf-8") as f:
                            f.write(fixed_source)
                            
            except Exception as comp_err:
                logger.error(f"Compilation execution failed: {comp_err}")
                if on_thinking:
                    await on_thinking(f"Compilation execution failed: {comp_err}\n", None, "PaperCompile", None)
                    
            compile_attempt += 1

        if not compiled_successfully:
            logger.warning(f"\nWarning: Failed to compile after {max_compile_attempts} attempts. Manual intervention may be required.")
            if on_thinking:
                await on_thinking(f"\nWarning: Failed to compile after {max_compile_attempts} attempts. Manual intervention may be required. Final source is available.\n", None, "PaperCompile", None)

        logger.info(f"\nPipeline complete! Final output saved in {output_dir}")
        if on_thinking:
            await on_thinking(f"\nPipeline complete! Final output saved in {output_dir}\n", None, "PaperAssemble", None)
            
        return {"content": final_latex, "pdf_url": pdf_url}

    except Exception as e:
        logger.exception(f"PaperAgent error: {e}")
        return {"content": f"Error generating paper: {str(e)}", "pdf_url": ""}
