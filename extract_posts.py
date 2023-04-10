import os
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import AtlasDB
from nomic import AtlasProject, login
from pyarrow import feather
import json
import requests
import bs4

from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from langchain.chains import LLMChain

from langchain.prompts import (
    ChatPromptTemplate,
    PromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema import AIMessage, HumanMessage, SystemMessage

ATLAS_TEST_API_KEY = "soH2CVoStCGvI5wW4vSVRFszgpPgImpnuHfiWewTBce_H"
project_name = "headline_data"

login(ATLAS_TEST_API_KEY)


def get_summary(persona):
    atlas = AtlasProject(
        name="headline_data_3",
    )

    projection = atlas.projections[0]
    projection._download_feather()

    data = feather.read_feather("tiles/0/0/0.feather")

    # data is a pandas dataframe with the column _topic_depth_1
    # get the _id field for for one entry in each topic
    ids = []
    for topic in data["_topic_depth_3"].unique():
        ids.append(data[data["_topic_depth_3"] == topic]["id_field"].iloc[0])

    ids = [str(x) for x in ids]

    headlines = atlas.get_data(ids)

    os.environ["OPENAI_API_KEY"] = "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"

    llm = OpenAI(temperature=0.9)

    system_message = "You are an AI system which determines whether a headline, tweet, or other source is of interest to an individual based on their stated preferences."
    system_message_prompt = SystemMessagePromptTemplate.from_template(system_message)
    human_template = """
    Below is the source:
    {headline}

    Below is the individual's stated preference:
    {preference_string}

    If the source seems relevant to the individual’s preference, say ["RELEVANT"]. If the source doesn't seem relevant or violates their preferences in any way, say ["IRRELEVANT"]
    """
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    chat_prompt = ChatPromptTemplate.from_messages(
        messages=[system_message_prompt, human_message_prompt]
    )

    chain1 = LLMChain(llm=llm, prompt=chat_prompt)

    relevant_headlines = []

    # save candidate headlines to json

    with open("candidate_headlines.json", "w") as f:
        json.dump(headlines, f)

    print(len(headlines))

    import concurrent.futures

    def process_headline(headline):
        test = chain1.run(
            headline=headline["embed_text"],
            preference_string=persona,
        )
        if "IRRELEVANT" not in test:
            return headline
        return None

    def parallelize_function(headlines):
        relevant_headlines = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(process_headline, headline): headline
                for headline in headlines
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    relevant_headlines.append(result)
        return relevant_headlines

    relevant_headlines = parallelize_function(headlines)

    print(len(relevant_headlines))

    # save relevant headlines to json
    with open("relevant_headlines.json", "w") as f:
        json.dump(relevant_headlines, f)

    # get the cached relevant headline data
    # with open("relevant_headlines.json", "r") as f:
    #     relevant_headlines = json.load(f)

    for headline in relevant_headlines:
        if (
            headline["feed_title"] != "Twitter Feed"
            and headline["feed_title"] != "Reddit Feed"
        ):
            print(headline["embed_text"])
            print(headline["feed_title"])
            print(headline["link"])
            # use beautiful soup to get the article text from the headline link
            r = requests.get(headline["link"])
            soup = bs4.BeautifulSoup(r.text, "html.parser")
            article = soup.text
            headline["article"] = article
            print(article)

    # save relevant headlines with article to json
    with open("relevant_headlines_with_article.json", "w") as f:
        json.dump(relevant_headlines, f)

    for headline in relevant_headlines:
        if (
            headline["feed_title"] != "Twitter Feed"
            and headline["feed_title"] != "Reddit Feed"
        ):
            print(headline["embed_text"])
            print(headline["feed_title"])
            print(headline["link"])
            # use beautiful soup to get the article text from the headline link
            r = requests.get(headline["link"])
            soup = bs4.BeautifulSoup(r.text, "html.parser")
            article = soup.text
            headline["article"] = article
            print(article)

    # # for the remianing, we get the full article and summerize it

    system_message = "You are an AI system which writes a summary of an article, tweet, or other source of information."
    system_message_prompt = SystemMessagePromptTemplate.from_template(system_message)
    human_template = """
    Below is the source:
    {article}

    Write a summary of this source. Do not make up or remove any information from the source. The summary should be succinct and no more than 2 sentences.
    """
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    chat_prompt = ChatPromptTemplate.from_messages(
        messages=[system_message_prompt, human_message_prompt]
    )

    chain1 = LLMChain(llm=llm, prompt=chat_prompt)

    for headline in relevant_headlines:
        # if the headline has the article field, we can summerize it
        if "article" in headline:
            test = chain1.run(
                article=headline["article"],
            )
            headline["summary"] = test

    # save relevant headlines with article to json
    with open("relevant_headlines_with_article_and_summary.json", "w") as f:
        json.dump(relevant_headlines, f)

    # # get the cached relevant headline data
    # with open("relevant_headlines_with_article_and_summary.json", "r") as f:
    #     relevant_headlines = json.load(f)

    # now we want to combine the headlines together

    system_message = "You are an AI system which combines summaries of multiple articles, tweets, or other sources of information into a single briefing."
    system_message_prompt = SystemMessagePromptTemplate.from_template(system_message)
    human_template = """
    Below is a list of summaries of information sources:
    {summaries}

    Combine these summaries into a single briefing. Do not make up any information. Only include noteworthy or newsworthy information. The summary should be easily digestible, information rich, and no more than 10 sentences. 
    """
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    chat_prompt = ChatPromptTemplate.from_messages(
        messages=[system_message_prompt, human_message_prompt]
    )

    chain1 = LLMChain(llm=llm, prompt=chat_prompt)

    source_string = "\n\n".join(
        [
            f"Source ({headline['feed_title']}):\n"
            + (headline["summary"] if "summary" in headline else "")
            for headline in relevant_headlines
        ]
    )

    summary = chain1.run(
        summaries=source_string,
    )

    return summary
