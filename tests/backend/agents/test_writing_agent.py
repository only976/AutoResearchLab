import pytest
import os
import json
from backend.paper.writing_agent import WritingAgent

class TestWritingAgent:
    @pytest.fixture
    def agent(self):
        return WritingAgent()

    def test_initialization(self, agent):
        assert agent is not None
    
    def test_generate_latex_paper(self, agent):
        """Test that generate_paper produces valid LaTeX format with complete structure."""
        # Path to test experiment data
        exp_dir = "/home/xiaoy/projects/AutoResearchLab/data/experiments/exp_20260213_202237_8e31b380"
        
        # Load plan data
        plan_path = os.path.join(exp_dir, "plan.json")
        if not os.path.exists(plan_path):
            pytest.skip("Missing test experiment data")
        with open(plan_path, "r") as f:
            plan_data = json.load(f)
        
        # Load conclusion data
        conclusion_path = os.path.join(exp_dir, "conclusion.json")
        if not os.path.exists(conclusion_path):
            pytest.skip("Missing test experiment data")
        with open(conclusion_path, "r") as f:
            conclusion_data = json.load(f)
        
        # Identify artifacts
        artifacts = []
        for file in os.listdir(exp_dir):
            if file.endswith(('.png', '.jpg', '.csv')):
                artifacts.append(file)
        
        # Generate paper in LaTeX format
        result = agent.generate_paper(
            plan_data, 
            conclusion_data, 
            artifacts, 
            format="latex"
        )
        
        # Verify result is not empty
        assert isinstance(result, str)
        assert len(result) > 0
        
        # Check for LaTeX document structure
        assert '\\documentclass' in result
        assert '\\begin{document}' in result
        assert '\\end{document}' in result
        
        # Check for complete paper sections
        required_elements = [
            '\\title',
            'abstract',
            '\\section{Introduction}',
            '\\section{Methodology}',
            '\\section{Results}',
            '\\section{Discussion}',
            '\\section{Conclusion}',
            '\\section*{References}',
            'Introduction',
            'Methodology',
            'Results',
            'Discussion',
            'Conclusion',
            'References'
        ]
        
        for element in required_elements:
            assert element in result, f"Missing element: {element}"
        
        # Check for artifact references
        import re
        for artifact in artifacts:
            if artifact.endswith('.png'):
                # Use regex to match \includegraphics with optional options
                pattern = r'\\includegraphics\[[^\]]*\]\{' + re.escape(artifact) + r'\}|\\includegraphics\{' + re.escape(artifact) + r'\}'
                assert re.search(pattern, result), f"Missing reference for artifact: {artifact}"
        
        # Check for consistent reference formatting
        # assert '\\begin{thebibliography}' in result
        # assert '\\end{thebibliography}' in result
        
        # Check that title is included
        if 'title' in plan_data:
            assert plan_data['title'] in result
        
        print("\nTest completed successfully!")
        print(f"Generated LaTeX paper length: {len(result)} characters")
        print(f"Included artifacts: {', '.join(artifacts)}")
