def chatResponse(body):
    request_arra = []
    request_arra.append(body)
    print(request_arra)
    if body:
        match body:
            case "1":
                response = """Bill Payments: 
                Select Your Biller?
                1. ZESA Prepaid
                2. Nyaradzo
                3. ZOL
                4. Telone
                5. Tertiary Institutions
                6. Cimas
                7. Insurance
                #. Home
                """
                
                return response
            case _:
                response =  """Good Morning Rivaldo, how can I help you today? 
                1. Account Balance Enquiry
                2. Purchase Airtime and Bundles
                3. Bill Payments
                4. Funds Transfer
                5. Visa Card / Mastercard Management
                6. City Hopper
                7. Account Services
                8. Ally Admin Services
                9. Customer Service
                10. News & Campaigns
                11. FAQs
                """
                return response
              
                
            