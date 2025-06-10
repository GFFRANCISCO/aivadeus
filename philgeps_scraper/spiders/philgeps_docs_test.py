import scrapy
from scrapy.http import FormRequest, Request
from urllib.parse import urljoin
import re
from supabase import create_client, Client
import uuid
from datetime import datetime
from dotenv import load_dotenv
import os
import logging
from pathlib import Path
import html



load_dotenv()

SUPABASE_URL = "https://vphtpzlbdcotorqpuonr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZwaHRwemxiZGNvdG9ycXB1b25yIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU1MDg0OTcsImV4cCI6MjA2MTA4NDQ5N30.XTP7clV__5ZVp9hZCJ2eGhL7HgEUeTcl2uINX0JC9WI"
SUPABASE_BUCKET = "bidding-projects"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class PhilgepsSpider(scrapy.Spider):
    name = "philgeps_docs"
    login_url = "https://notices.philgeps.gov.ph/GEPS/Login.aspx"
    start_urls = [
        "https://notices.philgeps.gov.ph/GEPS/Tender/OpportunitiesCatAgencySearchUI.aspx?ClickFrom=OpenOpp&EPSSubMenuID=10"
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch_id = f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}__{uuid.uuid4().hex[:6]}"
        self.seen_refs = set()  # Track (ref_no, batch_id)

         # Log the batch_id to a file and print it
        log_dir = Path("batch_logs")
        log_dir.mkdir(exist_ok=True)
        batch_log_file = log_dir / "latest_batch_id.txt"

        with open(batch_log_file, "w") as f:
            f.write(self.batch_id)

        self.logger.info(f" BATCH ID GENERATED: {self.batch_id}")
        print(f"\n PhilGEPS Spider started with BATCH ID: {self.batch_id}\n")

    def insert_to_supabase(self, data):
        record = {
            "ReferenceNo": data.get('ref_no'),
            "Entity": data.get('procuring_entity'),
            "Title": data.get('title'),
            "Classification": data.get('classification'),
            "category": data.get('category'),
            "ABC": data.get('budget'),
            "Summary": data.get('abstract'),
            "Status": data.get('status'),
            "PublishDate": data.get('published'),
            "ClosingDate": data.get('deadline'),
            "PageURL": data.get('Page_URL'),
            "REQT_LIST": data.get('REQT_LIST'),
            "batch_id": data.get('batch_id'),
            "created_at": data.get('created_at'),
        }

        try:
            response = supabase.table("BiddingDB").insert(record).execute()
            if response.error:
                self.logger.error(f"Supabase insert error for REF_NO {data.get('ref_no')}: {response.error}")
            else:
                self.logger.info(f"Inserted REF_NO {data.get('ref_no')} into Supabase.")
        except Exception as e:
            self.logger.error(f"Exception inserting REF_NO {data.get('ref_no')}: {e}")

    def parse(self, response):
        return FormRequest.from_response(
            response,
            formdata={
                'ctl00$ContentPlaceHolder1$txtUserName': 'Ddiversified3',
                'ctl00$ContentPlaceHolder1$txtPassword': 'deusdeus543',
                '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$btnLogin',
            },
            callback=self.after_login
        )

    def after_login(self, response):
        if "Invalid username or password" in response.text:
                self.logger.error("Login failed.")
                return
        self.logger.info("Login successful.")
        yield Request(
            url="https://notices.philgeps.gov.ph/GEPS/Tender/SplashOpenOpportunitiesUI.aspx?ClickFrom=OpenOpp&menuIndex=3",
            callback=self.parse_opportunities
        )

    def parse_opportunities(self, response):
        rows = response.xpath('//table[@id="dgSearchCatResult"]//tr')
        for row in rows:
            postback = row.xpath('.//a[contains(@id,"LinkButton1")]/@href').get()
            if postback:
                event_target = self.extract_event_target(postback)
                if event_target:
                    yield self.create_postback_request(response, event_target, self.parse_opportunity_list)

        next_page = response.xpath('//a[contains(@id,"pgCtrlOpp_nextLB")]/@href').get()
        if next_page:
            event_target = self.extract_event_target(next_page)
            if event_target:
                yield self.create_postback_request(response, event_target, self.parse_opportunities)

    def parse_opportunity_list(self, response):
        links = response.xpath('//a[contains(@id,"hyLinkTitle")]/@href').getall()
        for link in links:
            full_link = urljoin(response.url, link)
            yield Request(
                url=full_link,
                callback=self.parse_bid_notice,
                meta={'page_url': full_link},
                dont_filter=True
            )

        next_page = response.xpath('//a[contains(@id,"pgCtrlDetailedSearch_nextLB")]/@href').get()
        if next_page:
            event_target = self.extract_event_target(next_page)
            if event_target:
                yield self.create_postback_request(response, event_target, self.parse_opportunity_list)

    
    def extract_multiline_text(self, selector):
        """
        Extracts inner HTML and converts <br> tags to newlines, then strips other HTML.
        """
        raw_html = selector.get()
        if not raw_html:
            return None
        # Replace <br> or <br /> tags with newline
        text_with_newlines = re.sub(r'(<br\s*/?>)+', '\n', raw_html, flags=re.IGNORECASE)
        clean_text = re.sub(r'<[^>]+>', '', text_with_newlines)
        clean_text = html.unescape(clean_text)
        return clean_text.strip()

                

    def parse_bid_notice(self, response):
        ref_no = response.xpath('//span[@id="lblDisplayReferenceNo"]/text()').get()

        if not ref_no:
            self.logger.warning("Missing reference number on page: %s", response.url)
            return

        ref_key = (ref_no, self.batch_id)
        if ref_key in self.seen_refs:
            self.logger.info("Skipping already seen REF_NO: %s (batch: %s)", ref_no, self.batch_id)
            return

        # Optional persistent check against Supabase
        existing = supabase.table("BiddingDB").select("ReferenceNo", "batch_id").eq("ReferenceNo", ref_no).eq("batch_id", self.batch_id).execute()
        if existing.data:
            self.logger.info("REF_NO %s with batch_id %s already in Supabase, skipping.", ref_no, self.batch_id)
            return

        self.seen_refs.add(ref_key)

        raw_budget = response.xpath('//span[@id="lblDisplayBudget"]/text()').get()
        budget = self.clean_numeric_string(raw_budget)

        data = {
            'ref_no': ref_no,
            'type': response.xpath('//span[@id="lblHeader"]/text()').get(),
            'procuring_entity': response.xpath('//span[@id="lblDisplayProcuringEntity"]/text()').get(),
            'title': response.xpath('//span[@id="lblDisplayTitle"]/text()').get(),
            'classification': response.xpath('//span[@id="lblDisplayClass"]/text()').get(),
            'category': response.xpath('//span[@id="lblDisplayCategory"]/text()').get(),
            'budget': budget,
            'contact': response.xpath('//span[@id="lblDisplayContactPerson"]/text()').get(),
            'abstract': self.extract_multiline_text(response.xpath('//span[@id="lblAbstractText"]')),
            'status': response.xpath('//span[@id="lblDisplayStatus"]/text()').get(),
            'published': response.xpath('//span[@id="lblDisplayDatePublish"]/text()').get(),
            'deadline': response.xpath('//span[@id="lblDisplayCloseDateTime"]/text()').get(),
            'Page_URL': response.meta['page_url'],
            'REQT_LIST': [],
            'batch_id': self.batch_id,
            'created_at': datetime.utcnow().isoformat()
        }

        order_btn = response.xpath('//a[@id="lbtnNosOfAssoc"]/@href').get()
        if order_btn:
            event_target = self.extract_event_target(order_btn)
            if event_target:
                yield self.create_postback_request(
                    response,
                    event_target,
                    self.parse_order_table,
                    meta={'main_data': data}
                )
                return

        self.insert_to_supabase(data)
        yield data

    def clean_numeric_string(self, raw_str):
        if not raw_str:
            return None
        cleaned = re.sub(r'[^\d.]', '', raw_str)
        try:
            return float(cleaned)
        except ValueError:
            return None

    def parse_order_table(self, response):
        title_link = response.xpath('//div[contains(@class,"x-grid3-col-5")]/a')
        if title_link:
            yield Request(
                url=response.url,
                callback=self.click_continue_button_1,
                meta=response.meta,
                dont_filter=True
            )
        else:
            data = response.meta['main_data']
            self.logger.warning(f"[Order Basket] No title link found for REF_NO: {data['ref_no']} | URL: {data['Page_URL']}")
            self.insert_to_supabase(data)
            yield data

    def click_continue_button_1(self, response):
        return FormRequest.from_response(
            response,
            formdata={
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': response.xpath('//input[@id="__VIEWSTATE"]/@value').get(),
                '__EVENTVALIDATION': response.xpath('//input[@id="__EVENTVALIDATION"]/@value').get(),
                'btnCont': 'Continue',
            },
            callback=self.click_continue_button_2,
            meta=response.meta
        )

    def click_continue_button_2(self, response):
        if not response.xpath('//input[@id="btnContinueOrder"]'):
            data = response.meta['main_data']
            self.logger.warning(f"[Continue Order MISSING] for REF_NO: {data['ref_no']} | URL: {data['Page_URL']}")
            self.insert_to_supabase(data)
            yield data
            return

        yield FormRequest.from_response(
            response,
            formdata={
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': response.xpath('//input[@id="__VIEWSTATE"]/@value').get(),
                '__EVENTVALIDATION': response.xpath('//input[@id="__EVENTVALIDATION"]/@value').get(),
                'btnContinueOrder': 'Continue Order',
            },
            callback=self.extract_pdfs,
            meta=response.meta
        )

    def extract_pdfs(self, response):
        data = response.meta['main_data']
        data['REQT_LIST'] = []

        postback_links = response.xpath('//a[contains(@href, "__doPostBack")]/@href').getall()
        postbacks = [self.extract_event_target(href) for href in postback_links if 'ctl' in href]

        if not postbacks:
            self.insert_to_supabase(data)
            yield data
            return

        meta = {
            'main_data': data,
            'event_targets': postbacks,
            'current_index': 0
        }

        yield self.create_postback_request(response, postbacks[0], self.save_pdf, meta=meta)

    def save_pdf(self, response):
        data = response.meta['main_data']
        event_targets = response.meta['event_targets']
        index = response.meta['current_index']
        event_target = event_targets[index]

        content_type = response.headers.get('Content-Type', b'').decode('utf-8').lower()
        is_pdf = 'application/pdf' in content_type or response.body.startswith(b'%PDF')

        if is_pdf:
            filename = f"{data['ref_no']}_{event_target}.pdf"
            path = f"{SUPABASE_BUCKET}/{filename}"
            mime_type = "application/pdf"

            try:
                supabase.storage().from_(SUPABASE_BUCKET).upload(path, response.body, {"content-type": mime_type}, upsert=True)
                public_url = f"{SUPABASE_URL}/storage/v1/object/public/{path}"
                data['REQT_LIST'].append(public_url)
                self.logger.info(f"[SUCCESS] Uploaded PDF for REF_NO: {data['ref_no']} | File: {filename}")
            except Exception as e:
                self.logger.error(f"[UPLOAD FAILED] REF_NO: {data['ref_no']} | Target: {event_target} | Error: {e}")
        else:
            self.logger.error(f"[INVALID PDF] REF_NO: {data['ref_no']} | Event: {event_target} | Not a PDF")

        next_index = index + 1
        if next_index < len(event_targets):
            yield self.create_postback_request(
                response,
                event_targets[next_index],
                self.save_pdf,
                meta={
                    'main_data': data,
                    'event_targets': event_targets,
                    'current_index': next_index
                }
            )
        else:
            self.insert_to_supabase(data)
            yield data

    def create_postback_request(self, response, event_target, callback, meta=None):
        formdata = {
            '__EVENTTARGET': event_target,
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            '__VIEWSTATE': response.xpath('//input[@id="__VIEWSTATE"]/@value').get(),
            '__VIEWSTATEGENERATOR': response.xpath('//input[@id="__VIEWSTATEGENERATOR"]/@value').get(),
            '__EVENTVALIDATION': response.xpath('//input[@id="__EVENTVALIDATION"]/@value').get(),
        }
        return FormRequest(
            url=response.url,
            formdata=formdata,
            callback=callback,
            meta=meta or {},
            dont_filter=True
        )

    def extract_event_target(self, href):
        match = re.search(r"__doPostBack\('([^']+)'(?:,'([^']*)')?\)", href)
        return match.group(1) if match else None


    def start_requests(self):
        # Request to fetch the total count of opportunities
        yield scrapy.Request(
            url="https://notices.philgeps.gov.ph/GEPS/Tender/SplashOpportunitiesSearchUI.aspx?menuIndex=3&ClickFrom=OpenOpp&Result=3",
            callback=self.parse_total_count
        )

        # Continue with the normal scraping process
        for url in self.start_urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def parse_total_count(self, response):
        count_text = response.xpath(
            "//table[@id='pgCtrlDetailedSearch']//td[@align='right']//span/text()"
        ).get()

        if count_text:
            match = re.search(r"([\d,]+)", count_text)
            if match:
                total_opportunities = int(match.group(1).replace(",", ""))
                self.logger.info(f"Total opportunities found: {total_opportunities}")
            else:
                self.logger.warning("Could not extract number from count text.")
        else:
            self.logger.warning("Opportunity count text not found on the page.")

