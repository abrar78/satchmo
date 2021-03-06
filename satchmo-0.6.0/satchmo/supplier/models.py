"""
Used to manage raw inventory and supplier relationships.  This is still
under heavy development.
"""

from django.db import models
from django.utils.translation import ugettext_lazy as _
from satchmo.contact.models import Contact, Organization
import datetime

class RawItem(models.Model):
    """
    A raw good supplied by a supplier.  For instance, it could be a plain 
    shirt that you process to make your Item
    """
    supplier = models.ForeignKey(Organization)
    supplier_num = models.CharField(_("Supplier ID"), max_length=50)
    description = models.CharField(_("Description"), max_length=200)
    unit_cost = models.DecimalField(_("Unit Cost"), max_digits=6, decimal_places=2)
    inventory = models.IntegerField(_("Inventory"))
    
    def __unicode__(self):
        return self.description
    
    class Admin:
        list_display = ('supplier','description','supplier_num','inventory',)
        list_filter = ('supplier',)
    
    class Meta:
        verbose_name = _("Raw Item")
        verbose_name_plural = _("Raw Items")

class SupplierOrder(models.Model):
    """
    An order the store owner places to a supplier for a raw good.
    """
    supplier = models.ForeignKey(Organization)
    date_created = models.DateField(_("Date Created"))
    order_subtotal = models.DecimalField(_("Subtotal"), max_digits=6, decimal_places=2)
    order_shipping = models.DecimalField(_("Shipping"), max_digits=6, decimal_places=2)
    order_tax = models.DecimalField(_("Tax"), max_digits=6, decimal_places=2)
    order_notes = models.CharField(_("Notes"), max_length=200, blank=True)
    order_total = models.DecimalField(_("Total"), max_digits=6, decimal_places=2)
    
    def __unicode__(self):
        return unicode(self.date_created)
    
    def _status(self):
        return(self.supplierorderstatus_set.latest('date').status)
    status = property(_status)  
    
    def save(self):
        """Ensure we have a date_created before saving the first time."""
        if not self.id:
            self.date_created = datetime.date.today()
        super(SupplierOrder, self).save()
    
    
    class Admin:
        list_display = ('supplier','date_created', 'order_total','status')
        list_filter = ('date_created','supplier',)
        date_hierarchy = 'date_created'
    
    class Meta:
        verbose_name = _("Supplier Order")
        verbose_name_plural = _("Supplier Orders")
    
class SupplierOrderItem(models.Model):
    """
    Individual line items for an order
    """
    order = models.ForeignKey(SupplierOrder,edit_inline=models.TABULAR, num_in_admin=3)
    line_item = models.ForeignKey(RawItem, core=True)
    line_item_quantity = models.IntegerField(_("Line Item Quantity"), core=True)
    line_item_total = models.DecimalField(_("Line Item Total"), max_digits=6,decimal_places=2)
    
    def __unicode__(self):
        return unicode(self.line_item_total) 

SUPPLIERORDER_STATUS = (
    (_('Sent in'), _('Sent in')),
    (_('Shipped'), _('Shipped')),
    (_('Received'), _('Received')),
)

class SupplierOrderStatus(models.Model):
    """
    Status of a supplier's order.  There will be multiple statuses as it is
    placed and subsequently processed and received.
    """
    order = models.ForeignKey(SupplierOrder, edit_inline=models.STACKED, num_in_admin=1)
    status = models.CharField(_("Status"), max_length=20, choices=SUPPLIERORDER_STATUS, core=True, blank=True)
    notes = models.CharField(_("Notes"), max_length=100, blank=True)
    date = models.DateTimeField(blank=True)
    
    def __unicode__(self):
        return self.status
        
    class Meta:
        verbose_name = _("Supplier Order Status")
        verbose_name_plural = _("Supplier Order Statuses")

