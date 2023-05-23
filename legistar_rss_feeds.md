# All

## Month

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656727&GUID=75f36193-d132-4a58-902d-b83f9f775665&Mode=This+Month&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Month)

## Year

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656712&GUID=8f3d5335-8226-469f-b903-f576b95d2a94&Mode=This Year&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Year)

# P&Z

## Month

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656164&GUID=a30b2058-8bdd-486c-b13f-b1bcc22e54d2&Mode=This Month&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Month)

## Year

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656576&GUID=42e200b8-79ef-4ab0-8a47-1d56b156a90c&Mode=This Year&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Year)


# CC

## Month

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656317&GUID=8f332265-de3c-4b09-b87a-43616bf5aa55&Mode=This Month&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Month)

## Year

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656470&GUID=a0aad82c-8a8b-4045-b072-8936e7cdb51b&Mode=This Year&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Year)


# MPFDC

## Month

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656337&GUID=66a42b92-8b9f-4e5e-9996-1ebd413fa1b2&Mode=This Month&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Month)

## Year

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656689&GUID=a27e00a0-e829-4477-b09a-d53f603a035f&Mode=This Year&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Year)


# HLC

## Month

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656367&GUID=3ea8337a-da59-4fc3-9ff3-c4d3db374f8a&Mode=This Month&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Month)

## Year

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656682&GUID=67c9bad1-ce0a-48df-bfe0-ba994d5d8671&Mode=This Year&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Year)


# MEDC

## Month

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656389&GUID=488c182a-8be3-41f3-8616-b9fa3cdf1ada&Mode=This Month&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Month)

## Year

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656696&GUID=d320e1b3-85d2-4560-bfb0-a7d435dfcb82&Mode=This Year&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Year)


# ZBA

## Month

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656401&GUID=2b5745bc-9b94-4d71-8b71-812127b36630&Mode=This Month&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Month)

## Year

https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=20656701&GUID=5aed1c29-11dc-428b-92e2-21be19e8dd80&Mode=This Year&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Year)


# Random

## CC 5/22

From `All -> Month` feed above

### RSS List Link

https://mansfield.legistar.com/Gateway.aspx?M=MD&From=RSS&ID=1103650&GUID=A0588F30-62C3-4207-99CF-5AA1F35FC7F9

```python
path = '/Gateway.aspx'
query = {
    'M':'MD',
    'From':'RSS',
    'ID':'1103650',
    'GUID':'A0588F30-62C3-4207-99CF-5AA1F35FC7F9',
}
```

### RSS Detail

https://mansfield.legistar.com/Feed.ashx?M=CalendarDetail&ID=1103650&GUID=A0588F30-62C3-4207-99CF-5AA1F35FC7F9&Title=CITY+OF+MANSFIELD+-+Meeting+of+City+Council+on+5%2f22%2f2023+at+3%3a30+PM

```python
path = 'Feed.ashx'
query = {
    'M':'CalendarDetail',
    'ID':'1103650',
    'GUID':'A0588F30-62C3-4207-99CF-5AA1F35FC7F9',
    'Title':'...',
}
```

### Tranlation

```python
from yarl import URL
item_url = URL(feed_item.link)
qdict = {k:v for k,v in item_url.query.items()}
del qdict['From']
qdict['M'] = 'CalendarDetail'
real_item_url = item_url.with_path('/Feed.ashx').with_query(qdict)
```
