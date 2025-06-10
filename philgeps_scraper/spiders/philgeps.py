import scrapy
from scrapy.http import FormRequest, Request
from urllib.parse import urljoin
import re
import os
import requests
from supabase import create_client, Client
from mimetypes import guess_type

# Supabase configuration
SUPABASE_URL = "https://vphtpzlbdcotorqpuonr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZwaHRwemxiZGNvdG9ycXB1b25yIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU1MDg0OTcsImV4cCI6MjA2MTA4NDQ5N30.XTP7clV__5ZVp9hZCJ2eGhL7HgEUeTcl2uINX0JC9WI"  # Replace with full key
SUPABASE_BUCKET = "bidding-projects"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class PhilgepsSpider(scrapy.Spider):
    name = "philgeps"
    login_url = "https://notices.philgeps.gov.ph/GEPS/Login.aspx"
    start_urls = [
        "https://notices.philgeps.gov.ph/GEPS/Tender/OpportunitiesCatAgencySearchUI.aspx?ClickFrom=OpenOpp&EPSSubMenuID=10"
    ]

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

    def parse_bid_notice(self, response):
        data = {
            'type': response.xpath('//span[@id="lblHeader"]/text()').get(),
            'ref_no': response.xpath('//span[@id="lblDisplayReferenceNo"]/text()').get(),
            'procuring_entity': response.xpath('//span[@id="lblDisplayProcuringEntity"]/text()').get(),
            'title': response.xpath('//span[@id="lblDisplayTitle"]/text()').get(),
            'classification': response.xpath('//span[@id="lblDisplayClass"]/text()').get(),
            'category': response.xpath('//span[@id="lblDisplayCategory"]/text()').get(),
            'budget': response.xpath('//span[@id="lblDisplayBudget"]/text()').get(),
            'contact': response.xpath('//span[@id="lblDisplayContactPerson"]/text()').get(),
            'abstract': response.xpath('//span[@id="lblAbstractText"]/text()').get(),
            'status': response.xpath('//span[@id="lblDisplayStatus"]/text()').get(),
            'published': response.xpath('//span[@id="lblDisplayDatePublish"]/text()').get(),
            'deadline': response.xpath('//span[@id="lblDisplayCloseDateTime"]/text()').get(),
            'Page_URL': response.meta['page_url'],
            'REQT_LIST': []
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
        else:
            yield data

    def parse_order_table(self, response):
        row = response.xpath('//div[contains(@class,"x-grid3-cell-inner") and contains(@class,"x-grid3-col-5")]/a[1]')
        if row:
            yield Request(
                url=response.url,
                callback=self.click_continue_button,
                meta=response.meta,
                dont_filter=True
            )

    def click_continue_button(self, response):
        return FormRequest.from_response(
            response,
            formdata={
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': response.xpath('//input[@id="__VIEWSTATE"]/@value').get(),
                '__EVENTVALIDATION': response.xpath('//input[@id="__EVENTVALIDATION"]/@value').get(),
                'btnCont': 'Continue',
            },
            callback=self.extract_pdfs,
            meta=response.meta
        )

    def extract_pdfs(self, response):
        pdf_ids = response.xpath('//a[contains(@href, "PassValue")]/@href').re(r"PassValue\('(\d+)'\)")
        data = response.meta['main_data']

        for doc_id in pdf_ids:
            pdf_url = f"https://notices.philgeps.gov.ph/GEPS/Tender/SplashOrderAssocDocumentUI.aspx?DirectFrom=OpenOpp&AssociatedDocumentID={doc_id}"
            try:
                r = requests.get(pdf_url)
                r.raise_for_status()
                filename = f"{data['ref_no']}_{doc_id}.pdf"
                path = f"{SUPABASE_BUCKET}/{filename}"
                mime_type = guess_type(filename)[0] or "application/pdf"

                # Upload using Supabase Python client
                supabase.storage().from_(SUPABASE_BUCKET).upload(path, r.content, {"content-type": mime_type}, upsert=True)

                # Add public URL
                public_url = f"{SUPABASE_URL}/storage/v1/object/public/{path}"
                data['REQT_LIST'].append(public_url)

            except Exception as e:
                self.logger.warning(f"Upload failed for {doc_id}: {e}")

        yield data

    def extract_event_target(self, href_string):
        match = re.search(r"__doPostBack\('([^']+)'", href_string)
        return match.group(1) if match else None

    def create_postback_request(self, response, event_target, callback, meta=None):
        return FormRequest.from_response(
            response,
            formdata={
                '__EVENTTARGET': event_target,
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': response.xpath('//input[@id="__VIEWSTATE"]/@value').get(),
                '__EVENTVALIDATION': response.xpath('//input[@id="__EVENTVALIDATION"]/@value').get(),
            },
            callback=callback,
            meta=meta
        )
