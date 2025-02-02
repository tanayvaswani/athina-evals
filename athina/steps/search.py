# Step to make an external api call
import json
import time
from typing import Union, Dict, List, Any, Iterable, Optional
import requests
from athina.steps import Step
from jinja2 import Environment
from athina.helpers.jinja_helper import PreserveUndefined


def prepare_input_data(data):
    return {
        key: json.dumps(value) if isinstance(value, (list, dict)) else value
        for key, value in data.items()
    }


class Search(Step):
    """
    Step that makes a search API Call to https://exa.ai/.

    Attributes:
        query: The query string.
        type: The Type of search, 'keyword', 'neural', or 'auto' (decides between keyword and neural). Default neural.
        category: Optional data category to focus on, with higher comprehensivity and data cleanliness. Categories right now include company, research paper, news article, linkedin profile, github, tweet, movie, song, personal site, pdf and financial report.
        numResults: Optional number of search results to return. Default 10. Max 10 for basic plans. Up to thousands for custom plans.
        excludedDomains: Optional list of domains to exclude in the search. If specified, results will not include any from these domains.
        includedDomains: Optional list of domains to include in the search. If specified, results will only come from these domains..
        excludeText: Optional list of strings that must not be present in webpage text of results. Currently, only 1 string is supported, of up to 5 words.
        includeText: Optional list of strings that must be present in webpage text of results. Currently, only 1 string is supported, of up to 5 words.
        startPublishedDate: Optional start date for the search results. Format: YYYY-MM-DD.
        endPublishedDate: Optional end date for the search results. Format: YYYY-MM-DD.
        startCrawlDate: Optional Crawl date refers to the date that Exa discovered a link. Results will include links that were crawled after this date. Format: YYYY-MM-DD.
        endCrawlDate: Crawl date refers to the date that Exa discovered a link. Results will include links that were crawled before this date. Format: YYYY-MM-DD.
        highlights: Text snippets the LLM identifies as most relevant from each page.
        x_api_key: The API key to use for the request.
    """

    query: str
    type: Optional[str] = "neural"
    category: Optional[str] = None
    numResults: Optional[int] = 10
    excludeDomains: Optional[List[str]] = None
    includeDomains: Optional[List[str]] = None
    excludeText: Optional[List[str]] = None
    includeText: Optional[List[str]] = None
    startPublishedDate: Optional[str] = None
    endPublishedDate: Optional[str] = None
    startCrawlDate: Optional[str] = None
    endCrawlDate: Optional[str] = None
    highlights: Optional[Dict[str, Any]] = None

    x_api_key: str
    env: Environment = None

    class Config:
        arbitrary_types_allowed = True

    def execute(self, input_data: Any) -> Union[Dict[str, Any], None]:
        """Make an Search API call and return the response."""

        start_time = time.perf_counter()

        if input_data is None:
            input_data = {}

        if not isinstance(input_data, dict):
            return self._create_step_result(
                status="error",
                data="Input data must be a dictionary.",
                start_time=start_time,
            )
        # Create a custom Jinja2 environment with double curly brace delimiters and PreserveUndefined
        self.env = Environment(
            variable_start_string="{{",
            variable_end_string="}}",
            undefined=PreserveUndefined,
        )

        body = {
            "query": self.query,
            "type": self.type,
            "category": self.category,
            "numResults": self.numResults,
            "excludeDomains": self.excludeDomains,
            "includeDomains": self.includeDomains,
            "excludeText": self.excludeText,
            "includeText": self.includeText,
            "contents": {
                "highlights": {
                    "query": self.query,
                    **(self.highlights or {})  # Merging self.highlights if it exists, otherwise an empty dict
                },
                "summary": {"query": self.query},
            },
            "startPublishedDate": self.startPublishedDate,
            "endPublishedDate": self.endPublishedDate,
            "startCrawlDate": self.startCrawlDate,
            "endCrawlDate": self.endCrawlDate,
        }
        prepared_body = None
        # Add a filter to the Jinja2 environment to convert the input data to JSON
        body_template = self.env.from_string(json.dumps(body))
        prepared_input_data = prepare_input_data(input_data)
        prepared_body = body_template.render(**prepared_input_data)

        retries = 2  # number of retries
        timeout = 30  # seconds
        for attempt in range(retries):
            try:
                response = requests.post(
                    url="https://api.exa.ai/search",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.x_api_key,
                    },
                    json=(
                        json.loads(prepared_body, strict=False)
                        if prepared_body
                        else None
                    ),
                    timeout=timeout,
                )
                if response.status_code >= 400:
                    # If the status code is an error, return the error message
                    return self._create_step_result(
                        status="error",
                        data=f"Failed to make the API call.\nStatus code: {response.status_code}\nError:\n{response.text}",
                        start_time=start_time,
                    )
                try:
                    json_response = response.json()
                    # If the response is JSON, return the JSON data
                    return self._create_step_result(
                        status="success",
                        data=json_response,
                        start_time=start_time,
                    )
                except json.JSONDecodeError:
                    # If the response is not JSON, return the text
                    return self._create_step_result(
                        status="success",
                        data=response.text,
                        start_time=start_time,
                    )
            except requests.Timeout:
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                # If the request times out after multiple attempts, return an error message
                return self._create_step_result(
                    status="error",
                    data="Failed to make the API call.\nRequest timed out after multiple attempts.",
                    start_time=start_time,
                )
            except Exception as e:
                # If an exception occurs, return the error message
                return self._create_step_result(
                    status="error",
                    data=f"Failed to make the API call.\nError: {e.__class__.__name__}\nDetails:\n{str(e)}",
                    start_time=start_time,
                )
