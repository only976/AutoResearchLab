from pydantic import BaseModel, Field
from typing import List

# Define schemas for structured output
class OutlineSection(BaseModel):
    title: str = Field(description="The title of the section (e.g., Introduction, Methodology)")
    description: str = Field(description="A brief description of what this section should cover")
    key_points: List[str] = Field(description="Key bullet points to include in the section")
    required_context: List[str] = Field(description="Names of the specific context files needed to write this section (e.g., final_report.md, steps.txt)")
    images: List[str] = Field(default_factory=list, description="List of image filenames (e.g., 'figure1.png') to insert in this section. Every provided image must be allocated exactly once across all sections.")

class ReferenceItem(BaseModel):
    citation_key: str = Field(description="A unique BibTeX citation key (e.g., smith2020)")
    bibtex_entry: str = Field(description="The full BibTeX entry for this reference")

class PaperOutline(BaseModel):
    title: str = Field(description="The proposed title of the academic paper")
    sections: List[OutlineSection] = Field(description="The sections of the paper in logical order")
    references: List[ReferenceItem] = Field(default_factory=list, description="A list of unique references formatted as BibTeX entries, extracted from the reports")

class SectionRevision(BaseModel):
    section_title: str = Field(description="The exact title of the section that requires revision")
    feedback: str = Field(description="Specific feedback and required changes for this section")

class PaperReview(BaseModel):
    is_approved: bool = Field(description="Whether the draft is approved and ready for compilation")
    feedback: str = Field(description="Detailed feedback on the overall draft, focusing on consistency, logical flow, and formatting")
    required_revisions: List[SectionRevision] = Field(default_factory=list, description="Specific sections that need to be revised along with their feedback")

class EnrichedDraft(BaseModel):
    updated_draft: str = Field(description="The complete LaTeX draft with new \\cite{} commands inserted for common techniques")
    new_references: List[ReferenceItem] = Field(default_factory=list, description="A list of newly added classical references for the common techniques mentioned in the draft")
