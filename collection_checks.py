"""Non-blocking observations about dynamic website product counts."""


def listing_warning(driver, category_url, message):
    entry={'category_url':category_url,'message':message}
    warnings=getattr(driver,'collection_warnings',None)
    if warnings is None:
        warnings=[]
        driver.collection_warnings=warnings
    if entry not in warnings:
        warnings.append(entry)
    print('LISTING WARNING',category_url,message,flush=True)
