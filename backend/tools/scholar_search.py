from typing import Optional, Dict, List
import requests
import backoff

class OpenAlexSearchTool:
    def __init__(self, name: str = "SearchOpenAlex", description: str = "Search for relevant literature using OpenAlex.", max_results: int = 5):
        self.name = name
        self.description = description
        self.max_results = max_results

    def search(self, query: str) -> str:
        papers = search_for_papers(query, result_limit=self.max_results)
        if papers:
            return self.format_papers(papers)
        else:
            return "No papers found."

    def format_papers(self, papers: List[Dict]) -> str:
        paper_strings = []
        for i, paper in enumerate(papers):
            authors = ", ".join(
                [author.get("name", "Unknown") for author in paper.get("authors", [])]
            )
            paper_strings.append(
                f"""{i + 1}: {paper.get("title", "Unknown Title")}. {authors}. {paper.get("venue", "Unknown Venue")}, {paper.get("year", "Unknown Year")}.
Number of citations: {paper.get("citationCount", "N/A")}
Abstract: {paper.get("abstract", "No abstract available.")}"""
            )
        return "\n\n".join(paper_strings)

def reconstruct_abstract(inverted_index: Dict[str, List[int]]) -> str:
    if not inverted_index:
        return "No abstract available."
    max_index = 0
    for indices in inverted_index.values():
        if indices:
            max_index = max(max_index, max(indices))
    abstract_words = [""] * (max_index + 1)
    for word, indices in inverted_index.items():
        for index in indices:
            abstract_words[index] = word
    return " ".join(abstract_words)

@backoff.on_exception(
    backoff.expo,
    (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
    max_tries=5
)
def search_for_papers(query: str, result_limit: int = 10) -> Optional[List[Dict]]:
    if not query:
        return None
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per_page": result_limit,
        "sort": "cited_by_count:desc",
        "filter": "has_abstract:true"
    }
    headers = {
        "User-Agent": "mailto:example@example.com" 
    }
    try:
        rsp = requests.get(url, params=params, headers=headers)
        rsp.raise_for_status()
        data = rsp.json()
        results = data.get("results", [])
        if not results:
            return None
        papers = []
        for item in results:
            authors = []
            for authorship in item.get("authorships", []):
                if "author" in authorship:
                    authors.append({"name": authorship["author"].get("display_name", "Unknown")})
            
            venue = "Unknown Venue"
            if item.get("primary_location") and item["primary_location"].get("source"):
                 venue = item["primary_location"]["source"].get("display_name", "Unknown Venue")

            abstract_index = item.get("abstract_inverted_index")
            abstract = reconstruct_abstract(abstract_index) if abstract_index else "No abstract available."

            papers.append({
                "title": item.get("title", "Unknown Title"),
                "authors": authors,
                "venue": venue,
                "year": item.get("publication_year", "Unknown Year"),
                "citationCount": item.get("cited_by_count", 0),
                "abstract": abstract
            })
        return papers
    except Exception as e:
        print(f"Error searching OpenAlex: {e}")
        return None
