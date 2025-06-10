from pydantic import BaseModel

class BiddingRecord(BaseModel):
    ReferenceNo: str
    Entity: str
    Title: str
    Classification: str
    Category: str
    ABC: str
    Summary: str
    Status: str
    PublishDate: str
    ClosingDate: str
    PageURL: str
