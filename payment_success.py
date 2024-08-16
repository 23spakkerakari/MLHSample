"""
The modules have imported for different purpose mentioned as below:
render : to render an HTML template.
login_required : checking a user is authorized or not.
"""
import time
from django.shortcuts import render, redirect
from django.contrib import messages
from Services.models import Order, Cart, Notification, OrderItem
from decimal import Decimal
from django.conf import settings
import stripe
from Services.views.send_mail import send_notification_email
from datetime import datetime, timedelta
from weasyprint import HTML
import pdfkit
import pytz
import os
import random


stripe.api_key = settings.STRIPE_PUBLIC_KEY


def payment_success(request):
    """
    remove items into the cart for a successful payment.
    """
    order_id = request.session.get('order_id')
    print("Received order id: ", order_id)

    # PDF generation, etc., should really be done on a background thread.
    # Doing this is not worth it for the time being, though, given the overall state of the project.
    if order_id:
        try:
            eastern_time = datetime.now(pytz.timezone('US/Eastern'))

            order = Order.objects.get(orderID=order_id)
            cart_items = Cart.objects.filter(user=order.customer.user)

            for cart_item in cart_items:
                cart_item.delete()

            # Setup buyer email information
            buyer = order.customer.user
            buyer_email = order.customer.email
            buyer_email = buyer_email.strip()

            # Setup invoice & picklist HTML templates
            with open(os.path.join(settings.MEDIA_ROOT, "invoice_template.html")) as f:
                invoice_html = f.read()
            with open(os.path.join(settings.MEDIA_ROOT, "picklist_template.html")) as p:
                picklist_html = p.read()

            #ERROR CHANGE 1 7:24PM
            with open(os.path.join(settings.MEDIA_ROOT, "purchase_order_template.html")) as po:
                purchase_order_html = po.read()
            invoice_html = invoice_html.replace("BUYER_NAME", order.customer.name).replace("ORDER_ID", order_id)\
                .replace("BUYER_EMAIL", order.customer.email).replace("BUYER_ADDR_LINE1", order.customer.address.address_lane_1)\
                .replace("BUYER_CITY", order.customer.address.city)\
                .replace("BUYER_STATE", order.customer.address.state.state_name)\
                .replace("BUYER_ZIP", order.customer.address.zip_code)
            invoice_html = invoice_html.replace(
                "CURRENT_DATE", eastern_time.strftime("%B %d, %Y %I:%M %p"))
            
            ##CHANGE 1: 4:12PM
            invoice_html = invoice_html.replace(
                        "DUE_DATE", "Aug 15, 2024, 4:00pm")
            invoice_html = invoice_html.replace(
                        "PAYMENT_TERMS", str(order.payment))
            ##
            invoice_template_parts = invoice_html.split("DATA_GOES_HERE")

            


            picklist_html = picklist_html.replace("BUYER_NAME", order.customer.name).replace("ORDER_ID", order_id) \
                .replace("BUYER_EMAIL", order.customer.email).replace("BUYER_ADDR_LINE1", order.customer.address.address_lane_1) \
                .replace("BUYER_CITY", order.customer.address.city) \
                .replace("BUYER_STATE", order.customer.address.state.state_name) \
                .replace("BUYER_ZIP", order.customer.address.zip_code)
            picklist_html = picklist_html.replace(
                "CURRENT_DATE", eastern_time.strftime("%B %d, %Y %I:%M %p"))
            picklist_template_parts = picklist_html.split("DATA_GOES_HERE")


            ##cHANGE 2: 4:14pm
            #populating purchase order
            purchase_order_html = purchase_order_html.replace("BUYER_NAME", order.customer.name).replace("ORDER_ID", order_id)\
                .replace("BUYER_EMAIL", order.customer.email).replace("BUYER_ADDR_LINE1", order.customer.address.address_lane_1)\
                .replace("BUYER_CITY", order.customer.address.city)\
                .replace("BUYER_STATE", order.customer.address.state.state_name)\
                .replace("BUYER_ZIP", order.customer.address.zip_code)
            purchase_order_html = purchase_order_html.replace(
                        "DUE_DATE", "Aug 15, 2024, 4:00pm")
            purchase_order_html = purchase_order_html.replace(
                        "PAYMENT_TERMS", str(order.payment))           
            purchase_order_html = purchase_order_html.replace("CURRENT_DATE", eastern_time.strftime("%B %d, %Y %I:%M %p"))
            purchase_order_template_parts = purchase_order_html.split("DATA_GOES_HERE")

            ##

            # Seller Aggregation for Invoice Generation
            seller_agg = {}
            for prod in order.products.all():
                cur_seller_email = prod.supplier.email
                if cur_seller_email not in seller_agg.keys():
                    seller_agg[cur_seller_email] = {
                        'seller': prod.supplier, 'products': []}
                seller_agg[cur_seller_email]['products'].append(prod)

            # Generate invoices, picklists & send seller emails
            buyer_invoices = []

            # Iterate through the aggregated sellers (two loops instead of one for readability.
            for seller_email in seller_agg.keys():
                products_sold = {}
                for p in seller_agg[seller_email]['products']:
                    if p.product_title not in products_sold.keys():
                        products_sold[p.product_title] = 1
                    else:
                        products_sold[p.product_title] += 1

                # Select relevant order items (affiliated with the current supplier
                order_items = OrderItem.objects.filter(
                    order__orderID=order_id, product__supplier=seller_agg[seller_email]['seller'])
                cur_invoice_record_data = ""
                cur_picklist_record_data = ""
                cur_purchaseorder_record_data = "" #CHANGE 3 4:15PM
                cur_added_items = set()
                order_total = 0

                def get_safe_sku_packaged(v):
                    if v is None:
                        return "Standard (Unspecified)"
                    else:
                        if v.selling_option is None:
                            return "Standard (Unspecified)"
                        else:
                            return v.selling_option

                def get_safe_sku_unit(v):
                    if v is None:
                        return "Standard (Unspecified)"
                    else:
                        if v.unit_option is None:
                            return "Standard (Unspecified)"
                        else:
                            return v.unit_option

                # Iterate through order items, generating invoice records
                for order_item in order_items.all():
                    if order_item.product.product_title in cur_added_items:
                        continue
                    order_total += order_item.total_price * order_item.quantity
                    
                    ##CHANGE 4 7:26PM

                    cur_invoice_record_data += f"""
                        <tr class="item">
                            <td>{order_item.product.product_title}<br><small>{order_item.product.description}</small></td>
                            
                            <td class='qt'><p>{order_item.quantity} {get_safe_sku_unit(order_item.product.product_packaging.sku_unit)}<p></td>
                            
                            <td>${order_item.total_price}</td>
                            
                            <td>${order_item.total_price * order_item.quantity}</td>
                        </tr>
                    """

                    cur_picklist_record_data += f"""
                        <tr class="item">
                            <td>{order_item.product.product_title}</td>

                            <td>{order_item.quantity}</td>

                            <td>{get_safe_sku_packaged(order_item.product.product_packaging.sku_sold)}</td>
                            <td><div class="square"></div></td>
                            <td><div class="square"></div></td>
                            <td><div class="square"></div></td>
                        </tr>
                    """

                    cur_purchaseorder_record_data += f"""
                        <tr class="item">
                            <td>{order_item.product.product_title}<br><small>{order_item.product.description}</small></td>
                            <td class="qt"><p>{order_item.quantity}</p></td>
                        </tr>
                    """

                    ##


                    cur_added_items.add(order_item.product.product_title)
                # Prepare seller invoice pdf
                cur_seller_invoice_html = invoice_template_parts[0] + \
                    cur_invoice_record_data + invoice_template_parts[1]
                cur_seller_invoice_html = cur_seller_invoice_html.replace(
                    "SELLER_NAME", seller_agg[seller_email]['seller'].first_name + " " + seller_agg[seller_email]['seller'].last_name).replace("SELLER_EMAIL", seller_email)
                cur_seller_invoice_html = cur_seller_invoice_html.replace("GRAND_TOTAL", str(order_total)).replace(
                    "SELLER_COMPANY", seller_agg[seller_email]['seller'].company.company_name)
                cur_seller_invoice_file_name = "invoice_" + order_id + "__" + \
                    order.customer.name.replace(
                        " ", "") + "__" + str(time.time()) + ".pdf"
                cur_seller_full_file_save_path = os.path.join(
                    settings.MEDIA_ROOT, 'invoices', cur_seller_invoice_file_name)
               
                ##CHANGE 5 7:27PM
                HTML(string=cur_seller_invoice_html).write_pdf(cur_seller_full_file_save_path)               
                # pdfkit.from_string(cur_seller_invoice_html,
                #                    cur_seller_full_file_save_path, verbose=True)
                # Save invoice for buyer email
                buyer_invoices.append(cur_seller_full_file_save_path)

                # Prepare seller picklist pdf
                cur_seller_picklist_html = picklist_template_parts[0] + \
                    cur_picklist_record_data + picklist_template_parts[1]
                cur_seller_picklist_html = cur_seller_picklist_html.replace("SELLER_NAME", seller_agg[seller_email]['seller'].first_name + " " + seller_agg[seller_email]['seller'].last_name).replace(
                    "SELLER_EMAIL", seller_email).replace("SELLER_COMPANY", seller_agg[seller_email]['seller'].company.company_name)
                cur_seller_picklist_file_name = "picklist_" + order_id + "__" + \
                    order.customer.name.replace(
                        " ", "") + "__" + str(time.time()) + ".pdf"
                cur_seller_full_picklist_save_path = os.path.join(
                    settings.MEDIA_ROOT, 'picklists', cur_seller_picklist_file_name)
                
                ##CHANGE 6 7:28 PM
                HTML(string=cur_seller_picklist_html).write_pdf(cur_seller_full_picklist_save_path)
                # pdfkit.from_string(
                #     cur_seller_picklist_html, cur_seller_full_picklist_save_path, verbose=True)
                ####

                ##CHANGE 7 7:28 PM

                #Prepare seller purchase order pdf
                cur_seller_po_html = purchase_order_template_parts[0] + \
                    cur_purchaseorder_record_data + purchase_order_template_parts[1]
                cur_seller_po_html = cur_seller_po_html.replace(
                    "SELLER_NAME", seller_agg[seller_email]['seller'].first_name + " " + seller_agg[seller_email]['seller'].last_name).replace("SELLER_EMAIL", seller_email)
                cur_seller_po_html = cur_seller_po_html.replace("GRAND_TOTAL", str(order_total)).replace(
                    "SELLER_COMPANY", seller_agg[seller_email]['seller'].company.company_name)
                cur_seller_po_file_name = "po_" + order_id + "__" + \
                    order.customer.name.replace(
                        " ", "") + "__" + str(time.time()) + ".pdf"
                cur_seller_po_full_file_save_path = os.path.join(
                    settings.MEDIA_ROOT, 'purchase_orders', cur_seller_po_file_name)
                print(cur_seller_po_full_file_save_path)
                HTML(string=cur_seller_po_html).write_pdf(cur_seller_po_full_file_save_path)
                # pdfkit.from_string(cur_seller_po_html,
                #                    cur_seller_po_full_file_save_path, verbose=True)
                # Save invoice for buyer email

                ##
                buyer_invoices.append(cur_seller_po_full_file_save_path)



                cur_seller_msg = f"""
                Dear {seller_agg[seller_email]['seller'].first_name} {seller_agg[seller_email]['seller'].last_name},
                
                You just sold products on GustoMarket! Attached to this email, you will find an invoice for the transaction.
                
                Best,
                
                The GustoMarket Team
                """
                seller_notif, _ = Notification.objects.get_or_create(user=seller_agg[seller_email]['seller'].user,
                                                                     message=cur_seller_msg)

                # send_notification_email(seller_email, f"You just Sold Product on GustoMarket!", cur_seller_msg, [
                #                         cur_seller_full_file_save_path, cur_seller_full_picklist_save_path])  # Email seller
                
                ##CHANGE 8 7:29PM
                send_notification_email(seller_email, f"You just Sold Product on GustoMarket!", cur_seller_msg, [
                                        cur_seller_po_full_file_save_path, cur_seller_full_picklist_save_path])
            # Handle buyer notification/email
            buyer_msg = f"""
            Dear {order.customer.name},

            Thank you for your recent order with GustoMarket. The grand total of your order was ${order.grand_total}.

            Attached to this email, you will find your purchase invoices, separated by supplier.

            Best,

            The GustoMarket Team
            """
            buyer_notif, _ = Notification.objects.get_or_create(
                user=buyer, message=buyer_msg)
            # send_notification_email(buyer_email, "Thank you for your Purchase with GustoMarket!", buyer_msg,
            #                         buyer_invoices)  # Email buyer
            send_notification_email(buyer_email, "Thank you for your Purchase with GustoMarket!", buyer_msg,
                                    [cur_seller_po_full_file_save_path])

            print("Sent buyer email to ", buyer_email)
            # if str(request.GET.get("type")) == "cash":
            #     for cart_item in cart_items:
            #         cart_item.delete()
            # else:
            #     charge_id = stripe.PaymentIntent.retrieve(request.session.payment_intent)['latest_charge']
            #     # Delete cart items
            #     seller_payouts = {}
            #     for cart_item in cart_items:
            #         # STRIPE FLOW ADD ---------------
            #         product = cart_item.product
            #         quantity = cart_item.quantity
            #         total_price = Decimal(
            #             product.price_transport.amount) * Decimal(quantity)
            #         current_seller = product.supplier.stripe_account_id
            #         if current_seller not in seller_payouts.keys(): seller_payouts[current_seller] = {"amt": 0, "purpose": ""}
            #         seller_payouts[current_seller]["amt"] += total_price
            #         seller_payouts[current_seller]["purpose"] += str(quantity) + " " + str(product.product_title) + ", "
            #         # -------------------------------

            #         cart_item.delete()

            #     # STRIPE FLOW ADD ------------------
            #     # Pay sellers - one transfer object per seller
            #     for seller in seller_payouts.keys():
            #         cur_amt = seller_payouts[seller]["amt"] * Decimal(1 - settings.GUSTOMARKET_FEE) + Decimal(0.5) # Add 0.5 is for rounding purposes
            #         cur_purpose = seller_payouts[seller]["purpose"].removesuffix(", ")
            #         stripe.Transfer.create(
            #             amount=int(cur_amt),
            #             currency="usd",
            #             destination=seller,
            #             transfer_group=order_id,
            #             source_transaction=charge_id,
            #             metadata={"purpose": cur_purpose}
            #         )
            #     # -----------------------------------

            # Clear the session variable
            del request.session['order_id']

            # Display a confirmation message
            messages.success(
                request, 'Payment successful. Thank you for your order!')

            return render(request, 'payment_success.html', {'order': order})
        except Order.DoesNotExist:
            messages.error(request, 'Order not found.')
    else:
        messages.error(request, 'Invalid order ID.')

    # Redirect to the home page
    return redirect('/')


def payment_cancel(request):
    """
    return to the cart page for a cancel payment.
    """
    order_id = request.session.get('order_id')

    if order_id:
        try:
            order = Order.objects.get(orderID=order_id)
            order.payment_status = 'cancell'
            order.save()

            # Clear the session variable
            del request.session['order_id']

            # Display a confirmation message
            messages.success(
                request, 'Payment cancel!')

            return redirect('cart')

        except Order.DoesNotExist:
            messages.error(request, 'Order not found.')
    else:
        messages.error(request, 'Invalid order ID.')

    # Redirect to the home page
    return redirect('/')
