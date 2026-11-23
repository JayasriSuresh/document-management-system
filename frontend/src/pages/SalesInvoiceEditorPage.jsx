import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';
import InvoiceA4PreviewCanvas from '../components/InvoiceA4PreviewCanvas';

export const INVOICE_TYPES = [
  'Tax Invoice',
  'Invoice',
  'Bill of Supply',
  'Cash Memo',
  'Retail Invoice',
  'Export Invoice',
  'Proforma Invoice',
  'Credit Note',
  'Debit Note',
  'Receipt Voucher',
  'Payment Voucher',
  'Refund Voucher',
  'Revised Invoice',
  'Delivery Challan',
  'Other',
];

const INDIAN_STATES = [
  { code: '01', name: 'Jammu and Kashmir' },
  { code: '02', name: 'Himachal Pradesh' },
  { code: '03', name: 'Punjab' },
  { code: '04', name: 'Chandigarh' },
  { code: '05', name: 'Uttarakhand' },
  { code: '06', name: 'Haryana' },
  { code: '07', name: 'Delhi' },
  { code: '08', name: 'Rajasthan' },
  { code: '09', name: 'Uttar Pradesh' },
  { code: '10', name: 'Bihar' },
  { code: '11', name: 'Sikkim' },
  { code: '12', name: 'Arunachal Pradesh' },
  { code: '13', name: 'Nagaland' },
  { code: '14', name: 'Manipur' },
  { code: '15', name: 'Mizoram' },
  { code: '16', name: 'Tripura' },
  { code: '17', name: 'Meghalaya' },
  { code: '18', name: 'Assam' },
  { code: '19', name: 'West Bengal' },
  { code: '20', name: 'Jharkhand' },
  { code: '21', name: 'Odisha' },
  { code: '22', name: 'Chhattisgarh' },
  { code: '23', name: 'Madhya Pradesh' },
  { code: '24', name: 'Gujarat' },
  { code: '26', name: 'Dadra and Nagar Haveli and Daman and Diu' },
  { code: '27', name: 'Maharashtra' },
  { code: '29', name: 'Karnataka' },
  { code: '30', name: 'Goa' },
  { code: '31', name: 'Lakshadweep' },
  { code: '32', name: 'Kerala' },
  { code: '33', name: 'Tamil Nadu' },
  { code: '34', name: 'Puducherry' },
  { code: '35', name: 'Andaman and Nicobar Islands' },
  { code: '36', name: 'Telangana' },
  { code: '37', name: 'Andhra Pradesh' },
  { code: '38', name: 'Ladakh' },
  { code: '97', name: 'Other Territory' },
];

function formatCurrency(amount, currency = 'INR') {
  if (amount === undefined || amount === null || amount === '') return '₹0.00';
  const num = parseFloat(String(amount).replace(/[^0-9.-]+/g, ''));
  if (isNaN(num)) return `₹${amount}`;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: currency || 'INR',
    maximumFractionDigits: 2,
  }).format(num);
}

export default function SalesInvoiceEditorPage() {
  const { id } = useParams(); // If present, edit mode
  const { user } = useAuth();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // View mode tab: 'form' | 'preview'
  const [activeTab, setActiveTab] = useState('form');

  // Signatures state
  const [signatures, setSignatures] = useState([]);
  const [selectedSigIndex, setSelectedSigIndex] = useState(null);
  const [uploadingSig, setUploadingSig] = useState(false);

  // Dropdown master data
  const [gstRegistrations, setGstRegistrations] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [branches, setBranches] = useState([]);

  // Form state
  const [branchId, setBranchId] = useState('');
  const [gstRegistrationId, setGstRegistrationId] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [billingAddressId, setBillingAddressId] = useState('');
  const [shippingAddressId, setShippingAddressId] = useState('');
  const [sameAsBilling, setSameAsBilling] = useState(true);
  const [posStateCode, setPosStateCode] = useState('33');
  const [posStateName, setPosStateName] = useState('Tamil Nadu');
  const [invoiceType, setInvoiceType] = useState('Tax Invoice');
  const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().slice(0, 10));
  const [dueDate, setDueDate] = useState('');
  const [paymentTerms, setPaymentTerms] = useState('Net 30');
  const [termsAndConditions, setTermsAndConditions] = useState('1. Goods once sold will not be taken back.\n2. Payment due within specified credit terms.');
  const [notes, setNotes] = useState('');
  const [customerPoNumber, setCustomerPoNumber] = useState('');

  // Line items
  const [items, setItems] = useState([
    {
      item_order: 1,
      description: '',
      hsn_sac: '',
      quantity: 1,
      unit: 'nos',
      unit_price: 0,
      discount_amount: 0,
      gst_rate: 18,
      classification: 'goods',
    },
  ]);

  // Tax preview from authoritative backend calculation engine
  const [taxPreview, setTaxPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // New Customer Modal state
  const [showCustomerModal, setShowCustomerModal] = useState(false);
  const [newCustLegalName, setNewCustLegalName] = useState('');
  const [newCustTradeName, setNewCustTradeName] = useState('');
  const [newCustGstin, setNewCustGstin] = useState('');
  const [newCustPan, setNewCustPan] = useState('');
  const [newCustEmail, setNewCustEmail] = useState('');
  const [newCustPhone, setNewCustPhone] = useState('');
  const [newCustAddressLine1, setNewCustAddressLine1] = useState('');
  const [newCustCity, setNewCustCity] = useState('');
  const [newCustStateCode, setNewCustStateCode] = useState('33');
  const [newCustPincode, setNewCustPincode] = useState('');
  const [custModalError, setCustModalError] = useState('');

  // Load initial data
  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError('');
      try {
        const [gsts, custs] = await Promise.all([
          api.listGstRegistrations(),
          api.listCustomers(),
        ]);
        setGstRegistrations(gsts || []);
        setCustomers(custs || []);

        if (gsts && gsts.length > 0) {
          setGstRegistrationId(gsts[0].id);
        }

        // Set default branch from user
        if (user?.branch_id) {
          setBranchId(user.branch_id);
        }

        // If editing existing invoice
        if (id) {
          const invData = await api.getSalesInvoice(id);
          if (invData) {
            setBranchId(invData.branch_id || '');
            setGstRegistrationId(invData.gst_registration_id || (gsts[0]?.id || ''));
            setCustomerId(invData.customer_id || '');
            setBillingAddressId(invData.billing_address_id || '');
            setShippingAddressId(invData.shipping_address_id || '');
            setPosStateCode(invData.place_of_supply_state_code || '33');
            setPosStateName(invData.place_of_supply_state_name || 'Tamil Nadu');
            if (invData.invoice_date) setInvoiceDate(invData.invoice_date);
            if (invData.invoice_type) setInvoiceType(invData.invoice_type);
            if (invData.due_date) setDueDate(invData.due_date);
            if (invData.payment_terms) setPaymentTerms(invData.payment_terms);
            if (invData.terms_and_conditions) setTermsAndConditions(invData.terms_and_conditions);
            if (invData.notes) setNotes(invData.notes);
            if (invData.items && invData.items.length > 0) {
              setItems(
                invData.items.map((it, idx) => ({
                  item_order: idx + 1,
                  description: it.description || '',
                  hsn_sac: it.hsn_sac_code || it.hsn_sac || '',
                  quantity: parseFloat(it.quantity) || 1,
                  unit: it.unit || 'nos',
                  unit_price: parseFloat(it.unit_price) || 0,
                  discount_amount: parseFloat(it.discount_amount) || 0,
                  gst_rate: parseFloat(it.gst_rate) || 18,
                  classification: it.classification || 'goods',
                }))
              );
            }
            if (invData.signatures && Array.isArray(invData.signatures)) {
              setSignatures(
                invData.signatures.map((s) => ({
                  id: s.id,
                  storage_key: s.storage_key,
                  original_filename: s.original_filename,
                  mime_type: s.mime_type,
                  file_size: s.file_size,
                  sha256: s.sha256,
                  page_number: s.page_number || 1,
                  is_pinned_to_last_page: Boolean(s.is_pinned_to_last_page),
                  x_mm: parseFloat(s.x_mm) || 0,
                  y_mm: parseFloat(s.y_mm) || 0,
                  width_mm: parseFloat(s.width_mm) || 45,
                  height_mm: parseFloat(s.height_mm) || 25,
                  image_url: s.image_url,
                }))
              );
            }
          }
        }
      } catch (err) {
        setError(err.message || 'Failed to load initial invoice settings');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [id, user]);

  // Selected customer object & addresses
  const selectedCustomer = useMemo(() => {
    return customers.find((c) => String(c.id) === String(customerId));
  }, [customers, customerId]);

  // Auto-fill billing address and POS when customer changes
  useEffect(() => {
    if (selectedCustomer) {
      const addrs = selectedCustomer.addresses || [];
      const billing = addrs.find((a) => a.address_type === 'billing') || addrs[0];
      if (billing) {
        setBillingAddressId(billing.id);
        if (sameAsBilling) {
          setShippingAddressId(billing.id);
        }
        if (billing.state_code) {
          setPosStateCode(billing.state_code);
          const st = INDIAN_STATES.find((s) => s.code === billing.state_code);
          if (st) setPosStateName(st.name);
          else if (billing.state) setPosStateName(billing.state);
        }
      }
    }
  }, [selectedCustomer, sameAsBilling]);

  // Handle POS State Code change
  const handlePosChange = (code) => {
    setPosStateCode(code);
    const st = INDIAN_STATES.find((s) => s.code === code);
    if (st) setPosStateName(st.name);
  };

  // Trigger tax engine preview on change
  const runTaxPreview = useCallback(async () => {
    const activeGst = gstRegistrations.find((g) => String(g.id) === String(gstRegistrationId));
    const sellerState = activeGst ? activeGst.state_code : '33';

    // Filter valid items
    const validItems = items
      .filter((it) => it.description.trim() && parseFloat(it.unit_price) >= 0)
      .map((it, idx) => ({
        item_order: idx + 1,
        description: it.description,
        hsn_sac: it.hsn_sac,
        quantity: parseFloat(it.quantity) || 1,
        unit: it.unit || 'nos',
        unit_price: parseFloat(it.unit_price) || 0,
        discount_amount: parseFloat(it.discount_amount) || 0,
        gst_rate: parseFloat(it.gst_rate) || 0,
        classification: it.classification || 'goods',
      }));

    if (validItems.length === 0) {
      setTaxPreview(null);
      return;
    }

    setPreviewLoading(true);
    try {
      const res = await api.previewSalesTax({
        seller_state_code: sellerState,
        place_of_supply_state_code: posStateCode || '33',
        items: validItems,
        apply_round_off: false,
      });
      setTaxPreview(res);
    } catch (err) {
      console.warn('Tax preview failed:', err.message);
    } finally {
      setPreviewLoading(false);
    }
  }, [items, gstRegistrationId, gstRegistrations, posStateCode]);

  useEffect(() => {
    const timer = setTimeout(() => {
      runTaxPreview();
    }, 300);
    return () => clearTimeout(timer);
  }, [runTaxPreview]);

  // Line item manipulation
  const handleItemChange = (index, field, value) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index], [field]: value };
    setItems(newItems);
  };

  const addItemRow = () => {
    setItems([
      ...items,
      {
        item_order: items.length + 1,
        description: '',
        hsn_sac: '',
        quantity: 1,
        unit: 'nos',
        unit_price: 0,
        discount_amount: 0,
        gst_rate: 18,
        classification: 'goods',
      },
    ]);
  };

  const removeItemRow = (index) => {
    if (items.length <= 1) return;
    const filtered = items.filter((_, idx) => idx !== index);
    setItems(filtered.map((it, idx) => ({ ...it, item_order: idx + 1 })));
  };

  // Quick Customer Creation
  const handleCreateCustomer = async (e) => {
    e.preventDefault();
    setCustModalError('');
    if (!newCustLegalName.trim()) {
      setCustModalError('Customer Legal Name is required');
      return;
    }
    try {
      const payload = {
        legal_name: newCustLegalName.trim(),
        trade_name: newCustTradeName.trim() || newCustLegalName.trim(),
        gstin: newCustGstin.trim() ? newCustGstin.trim().toUpperCase() : null,
        pan: newCustPan.trim() ? newCustPan.trim().toUpperCase() : null,
        email: newCustEmail.trim() || null,
        phone: newCustPhone.trim() || null,
        address: newCustAddressLine1.trim()
          ? {
              address_line1: newCustAddressLine1.trim(),
              city: newCustCity.trim() || 'Chennai',
              state: INDIAN_STATES.find((s) => s.code === newCustStateCode)?.name || 'Tamil Nadu',
              state_code: newCustStateCode,
              pincode: newCustPincode.trim() || '600001',
              address_type: 'billing',
            }
          : null,
      };
      const created = await api.createCustomer(payload);
      setCustomers([...customers, created]);
      setCustomerId(created.id);
      if (created.addresses && created.addresses.length > 0) {
        setBillingAddressId(created.addresses[0].id);
        setShippingAddressId(created.addresses[0].id);
        setPosStateCode(created.addresses[0].state_code);
        setPosStateName(created.addresses[0].state);
      }
      setShowCustomerModal(false);
      // Reset modal inputs
      setNewCustLegalName('');
      setNewCustTradeName('');
      setNewCustGstin('');
      setNewCustPan('');
      setNewCustEmail('');
      setNewCustPhone('');
      setNewCustAddressLine1('');
      setNewCustCity('');
      setNewCustPincode('');
    } catch (err) {
      setCustModalError(err.message || 'Failed to create customer');
    }
  };

  // Signature Event Handlers
  const handleAddSignatureFile = async (file, currentPage = 1) => {
    setError('');
    setUploadingSig(true);
    try {
      const res = await api.uploadTemporarySignature(file);
      const newSig = {
        upload_token: res.upload_token,
        temp_view_url: res.temp_view_url,
        aspect_ratio: parseFloat(res.aspect_ratio) || 1.8,
        page_number: currentPage || 1,
        is_pinned_to_last_page: false,
        x_mm: 145.0,
        y_mm: 245.0,
        width_mm: parseFloat(res.default_width_mm) || 45.0,
        height_mm: parseFloat(res.default_height_mm) || 25.0,
      };
      setSignatures((prev) => [...prev, newSig]);
      setSelectedSigIndex(signatures.length);
      setSuccessMsg('Signature uploaded! Drag and resize it anywhere on the page.');
    } catch (err) {
      setError(err.message || 'Failed to upload signature image');
    } finally {
      setUploadingSig(false);
    }
  };

  const handleUpdateSignature = (index, updatedFields) => {
    setSignatures((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], ...updatedFields };
      return copy;
    });
  };

  const handleDeleteSignature = (index) => {
    setSignatures((prev) => prev.filter((_, i) => i !== index));
    if (selectedSigIndex === index) {
      setSelectedSigIndex(null);
    } else if (selectedSigIndex > index) {
      setSelectedSigIndex(selectedSigIndex - 1);
    }
  };

  // Save Draft
  const handleSaveDraft = async () => {
    setError('');
    setSuccessMsg('');
    if (!customerId) {
      setError('Please select or add a Customer');
      return;
    }
    if (!gstRegistrationId) {
      setError('Please select a GST Registration');
      return;
    }
    const validItems = items.filter((it) => it.description.trim());
    if (validItems.length === 0) {
      setError('Please enter at least one line item with a description');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        branch_id: branchId ? parseInt(branchId, 10) : user?.branch_id,
        gst_registration_id: parseInt(gstRegistrationId, 10),
        customer_id: parseInt(customerId, 10),
        billing_address_id: billingAddressId ? parseInt(billingAddressId, 10) : null,
        shipping_address_id: (sameAsBilling ? billingAddressId : shippingAddressId)
          ? parseInt(sameAsBilling ? billingAddressId : shippingAddressId, 10)
          : null,
        place_of_supply: posStateCode,
        place_of_supply_state_code: posStateCode,
        place_of_supply_state_name: posStateName,
        invoice_type: invoiceType || 'Tax Invoice',
        invoice_date: invoiceDate,
        due_date: dueDate || null,
        payment_terms: paymentTerms,
        terms_and_conditions: termsAndConditions,
        notes: notes,
        signatures: signatures.map((s) => ({
          id: s.id || null,
          upload_token: s.upload_token || null,
          page_number: s.page_number || 1,
          is_pinned_to_last_page: Boolean(s.is_pinned_to_last_page),
          x_mm: Number(s.x_mm),
          y_mm: Number(s.y_mm),
          width_mm: Number(s.width_mm),
          height_mm: Number(s.height_mm),
        })),
        items: validItems.map((it, idx) => ({
          item_order: idx + 1,
          description: it.description,
          hsn_sac_code: it.hsn_sac || null,
          quantity: parseFloat(it.quantity) || 1,
          unit: it.unit || 'nos',
          unit_price: parseFloat(it.unit_price) || 0,
          discount_amount: parseFloat(it.discount_amount) || 0,
          gst_rate: parseFloat(it.gst_rate) || 0,
          classification: it.classification || 'goods',
        })),
      };

      let result;
      if (id) {
        result = await api.updateSalesInvoiceDraft(id, payload);
        setSuccessMsg('Sales Invoice draft updated successfully!');
        if (result?.signatures) {
          setSignatures(
            result.signatures.map((s) => ({
              id: s.id,
              storage_key: s.storage_key,
              original_filename: s.original_filename,
              mime_type: s.mime_type,
              file_size: s.file_size,
              sha256: s.sha256,
              page_number: s.page_number || 1,
              is_pinned_to_last_page: Boolean(s.is_pinned_to_last_page),
              x_mm: parseFloat(s.x_mm) || 0,
              y_mm: parseFloat(s.y_mm) || 0,
              width_mm: parseFloat(s.width_mm) || 45,
              height_mm: parseFloat(s.height_mm) || 25,
              image_url: s.image_url,
            }))
          );
        }
      } else {
        result = await api.createSalesInvoiceDraft(payload);
        setSuccessMsg('Sales Invoice draft created successfully!');
        if (result?.id) {
          navigate(`/invoices/edit/${result.id}`);
        } else {
          navigate(`/invoices`);
        }
      }
    } catch (err) {
      setError(err.message || 'Failed to save sales invoice draft');
    } finally {
      setSaving(false);
    }
  };

  // Submit for Approval
  const handleSubmitForApproval = async () => {
    setError('');
    setSuccessMsg('');
    if (!customerId) {
      setError('Please select or add a Customer');
      return;
    }
    const validItems = items.filter((it) => it.description.trim());
    if (validItems.length === 0) {
      setError('Please enter at least one line item');
      return;
    }

    setSubmitting(true);
    try {
      // First save draft
      const payload = {
        branch_id: branchId ? parseInt(branchId, 10) : user?.branch_id,
        gst_registration_id: parseInt(gstRegistrationId, 10),
        customer_id: parseInt(customerId, 10),
        billing_address_id: billingAddressId ? parseInt(billingAddressId, 10) : null,
        shipping_address_id: (sameAsBilling ? billingAddressId : shippingAddressId)
          ? parseInt(sameAsBilling ? billingAddressId : shippingAddressId, 10)
          : null,
        place_of_supply: posStateCode,
        place_of_supply_state_code: posStateCode,
        place_of_supply_state_name: posStateName,
        invoice_type: invoiceType || 'Tax Invoice',
        invoice_date: invoiceDate,
        due_date: dueDate || null,
        payment_terms: paymentTerms,
        terms_and_conditions: termsAndConditions,
        notes: notes,
        signatures: signatures.map((s) => ({
          id: s.id || null,
          upload_token: s.upload_token || null,
          page_number: s.page_number || 1,
          is_pinned_to_last_page: Boolean(s.is_pinned_to_last_page),
          x_mm: Number(s.x_mm),
          y_mm: Number(s.y_mm),
          width_mm: Number(s.width_mm),
          height_mm: Number(s.height_mm),
        })),
        items: validItems.map((it, idx) => ({
          item_order: idx + 1,
          description: it.description,
          hsn_sac_code: it.hsn_sac || null,
          quantity: parseFloat(it.quantity) || 1,
          unit: it.unit || 'nos',
          unit_price: parseFloat(it.unit_price) || 0,
          discount_amount: parseFloat(it.discount_amount) || 0,
          gst_rate: parseFloat(it.gst_rate) || 0,
          classification: it.classification || 'goods',
        })),
      };

      let targetId = id;
      if (targetId) {
        await api.updateSalesInvoiceDraft(targetId, payload);
      } else {
        const created = await api.createSalesInvoiceDraft(payload);
        targetId = created.id;
      }

      // Submit for approval
      await api.submitSalesInvoice(targetId);
      setSuccessMsg('Invoice submitted for approval! An authorized approver must approve it before issuance.');
      setTimeout(() => {
        navigate('/invoices');
      }, 1500);
    } catch (err) {
      setError(err.message || 'Failed to submit sales invoice for approval');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="page-content" style={{ textAlign: 'center', padding: '4rem' }}>
        <div className="spinner" />
        <p style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Loading invoice builder…</p>
      </div>
    );
  }

  const activeGst = gstRegistrations.find((g) => String(g.id) === String(gstRegistrationId));
  const isInterState = activeGst ? activeGst.state_code !== posStateCode : false;

  return (
    <div className="page-content" style={{ maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <div className="page-header" style={{ marginBottom: '1.5rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <span
              style={{
                background: '#047857',
                color: '#fff',
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '0.2rem 0.5rem',
                borderRadius: 'var(--radius-sm)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Sales Invoice
            </span>
            <h2 className="page-title" style={{ margin: 0 }}>
              {id ? `Edit Sales Invoice #${id}` : 'Create Outbound Sales Invoice'}
            </h2>
          </div>
          <p className="page-subtitle">
            Generate GST-compliant tax invoices with deterministic Decimal calculations and gapless consecutive numbering.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-secondary" onClick={() => navigate('/invoices')}>
            Cancel
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleSaveDraft}
            disabled={saving || submitting}
          >
            {saving ? 'Saving…' : 'Save as Draft'}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSubmitForApproval}
            disabled={saving || submitting}
          >
            {submitting ? 'Submitting…' : 'Submit for Approval'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: '1.5rem' }}>{error}</div>}
      {successMsg && <div className="alert alert-success" style={{ marginBottom: '1.5rem' }}>{successMsg}</div>}

      {/* View Mode Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '2px solid var(--border)', paddingBottom: '0.5rem' }}>
        <button
          type="button"
          onClick={() => setActiveTab('form')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.5rem 1rem',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            background: activeTab === 'form' ? 'var(--brand)' : 'transparent',
            color: activeTab === 'form' ? '#fff' : 'var(--text-secondary)',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          <span>📝</span>
          <span>Invoice Details & Items</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('preview')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.5rem 1rem',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            background: activeTab === 'preview' ? 'var(--brand)' : 'transparent',
            color: activeTab === 'preview' ? '#fff' : 'var(--text-secondary)',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          <span>🖋️</span>
          <span>Visual Layout & Signatures</span>
          {signatures.length > 0 && (
            <span
              style={{
                backgroundColor: activeTab === 'preview' ? '#fff' : 'var(--brand)',
                color: activeTab === 'preview' ? 'var(--brand)' : '#fff',
                fontSize: '0.6875rem',
                fontWeight: 700,
                borderRadius: '10px',
                padding: '0.1rem 0.45rem',
              }}
            >
              {signatures.length}
            </span>
          )}
        </button>
      </div>

      {activeTab === 'preview' && (
        <InvoiceA4PreviewCanvas
          invoiceId={id ? parseInt(id, 10) : null}
          signatures={signatures}
          selectedSigIndex={selectedSigIndex}
          onSelectSig={setSelectedSigIndex}
          onUpdateSig={handleUpdateSignature}
          onDeleteSig={handleDeleteSignature}
          onAddSignatureFile={handleAddSignatureFile}
          uploading={uploadingSig}
        />
      )}

      {/* Main Form Layout */}
      {activeTab === 'form' && (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '1.5rem', alignItems: 'start' }}>
        {/* Left Column: Form Details */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Card 1: Parties & Place of Supply */}
          <div className="table-container" style={{ padding: '1.5rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
              1. Seller & Customer Details
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1rem' }}>
              {/* Seller GSTIN */}
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Seller GST Registration *</label>
                <select
                  className="form-control"
                  value={gstRegistrationId}
                  onChange={(e) => setGstRegistrationId(e.target.value)}
                >
                  {gstRegistrations.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.gstin} ({g.legal_name || g.trade_name}) - State: {g.state_code}
                    </option>
                  ))}
                </select>
                {activeGst && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                    Registered: {activeGst.address_line1}, {activeGst.city} ({activeGst.state_name})
                  </p>
                )}
              </div>

              {/* Customer */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label className="form-label" style={{ fontWeight: 600 }}>Customer (Billed To) *</label>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.1rem 0.4rem', color: 'var(--brand)' }}
                    onClick={() => setShowCustomerModal(true)}
                  >
                    + New Customer
                  </button>
                </div>
                <select
                  className="form-control"
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                >
                  <option value="">-- Select Customer --</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.legal_name} {c.gstin ? `[GSTIN: ${c.gstin}]` : '(Unregistered)'}
                    </option>
                  ))}
                </select>
                {selectedCustomer?.gstin && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                    GSTIN: <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{selectedCustomer.gstin}</span>
                  </p>
                )}
              </div>
            </div>

            {/* Place of Supply & Billing Address */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', paddingTop: '0.5rem', borderTop: '1px dashed var(--border)' }}>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Place of Supply (State) *</label>
                <select
                  className="form-control"
                  value={posStateCode}
                  onChange={(e) => handlePosChange(e.target.value)}
                >
                  {INDIAN_STATES.map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.code} - {s.name}
                    </option>
                  ))}
                </select>
                <div style={{ marginTop: '0.35rem' }}>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '0.2rem 0.5rem',
                      borderRadius: 'var(--radius-sm)',
                      background: isInterState ? '#eff6ff' : '#f0fdf4',
                      color: isInterState ? '#1d4ed8' : '#15803d',
                      border: `1px solid ${isInterState ? '#bfdbfe' : '#bbf7d0'}`,
                      display: 'inline-block',
                    }}
                  >
                    {isInterState ? '🌐 Inter-State Supply (IGST Applicable)' : '🏢 Intra-State Supply (CGST + SGST Applicable)'}
                  </span>
                </div>
              </div>

              {/* Billing Address Selection */}
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Billing Address</label>
                {selectedCustomer?.addresses && selectedCustomer.addresses.length > 0 ? (
                  <select
                    className="form-control"
                    value={billingAddressId}
                    onChange={(e) => setBillingAddressId(e.target.value)}
                  >
                    {selectedCustomer.addresses.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.address_line1}, {a.city}, {a.state} ({a.pincode})
                      </option>
                    ))}
                  </select>
                ) : (
                  <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                    No saved addresses. Customer default address will be used.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Card 2: Invoice Dates & Metadata */}
          <div className="table-container" style={{ padding: '1.5rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
              2. Invoice Dates & Terms
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Invoice Type *</label>
                <select
                  className="form-control"
                  value={invoiceType}
                  onChange={(e) => setInvoiceType(e.target.value)}
                >
                  {INVOICE_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Invoice Date *</label>
                <input
                  type="date"
                  className="form-control"
                  value={invoiceDate}
                  onChange={(e) => setInvoiceDate(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Due Date</label>
                <input
                  type="date"
                  className="form-control"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Payment Terms</label>
                <input
                  type="text"
                  className="form-control"
                  value={paymentTerms}
                  placeholder="e.g. Net 30"
                  onChange={(e) => setPaymentTerms(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Buyer PO / Ref</label>
                <input
                  type="text"
                  className="form-control"
                  value={customerPoNumber}
                  placeholder="e.g. PO-2026-99"
                  onChange={(e) => setCustomerPoNumber(e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* Card 3: Dynamic Line Items */}
          <div className="table-container" style={{ padding: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  3. Line Items
                </h3>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', margin: 0 }}>
                  Add products or services with HSN/SAC codes, quantities, and GST rates.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={addItemRow}
              >
                + Add Item
              </button>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table className="doc-table" style={{ fontSize: '0.875rem' }}>
                <thead>
                  <tr>
                    <th style={{ width: '40px' }}>#</th>
                    <th style={{ minWidth: '180px' }}>Description *</th>
                    <th style={{ width: '90px' }}>HSN/SAC</th>
                    <th style={{ width: '70px' }}>Qty</th>
                    <th style={{ width: '80px' }}>Unit</th>
                    <th style={{ width: '100px' }}>Rate (₹)</th>
                    <th style={{ width: '80px' }}>Disc (₹)</th>
                    <th style={{ width: '80px' }}>GST %</th>
                    <th style={{ width: '100px', textAlign: 'right' }}>Total (₹)</th>
                    <th style={{ width: '40px' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it, idx) => {
                    const rowPreview = taxPreview?.items?.[idx];
                    const rowTotal = rowPreview ? rowPreview.total : ((parseFloat(it.quantity) || 0) * (parseFloat(it.unit_price) || 0) - (parseFloat(it.discount_amount) || 0));

                    return (
                      <tr key={idx}>
                        <td style={{ fontWeight: 600, color: 'var(--text-muted)' }}>{idx + 1}</td>
                        <td>
                          <input
                            type="text"
                            className="form-control form-control-sm"
                            placeholder="Item or service description"
                            value={it.description}
                            onChange={(e) => handleItemChange(idx, 'description', e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className="form-control form-control-sm"
                            placeholder="8528"
                            value={it.hsn_sac}
                            onChange={(e) => handleItemChange(idx, 'hsn_sac', e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min="0.01"
                            className="form-control form-control-sm"
                            value={it.quantity}
                            onChange={(e) => handleItemChange(idx, 'quantity', e.target.value)}
                          />
                        </td>
                        <td>
                          <select
                            className="form-control form-control-sm"
                            value={it.unit}
                            onChange={(e) => handleItemChange(idx, 'unit', e.target.value)}
                          >
                            <option value="nos">nos</option>
                            <option value="pcs">pcs</option>
                            <option value="hours">hours</option>
                            <option value="box">box</option>
                            <option value="kg">kg</option>
                            <option value="meters">meters</option>
                            <option value="set">set</option>
                          </select>
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className="form-control form-control-sm"
                            value={it.unit_price}
                            onChange={(e) => handleItemChange(idx, 'unit_price', e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className="form-control form-control-sm"
                            value={it.discount_amount}
                            onChange={(e) => handleItemChange(idx, 'discount_amount', e.target.value)}
                          />
                        </td>
                        <td>
                          <select
                            className="form-control form-control-sm"
                            value={it.gst_rate}
                            onChange={(e) => handleItemChange(idx, 'gst_rate', e.target.value)}
                          >
                            <option value="0">0%</option>
                            <option value="5">5%</option>
                            <option value="12">12%</option>
                            <option value="18">18%</option>
                            <option value="28">28%</option>
                          </select>
                        </td>
                        <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--text-primary)' }}>
                          {formatCurrency(rowTotal)}
                        </td>
                        <td>
                          {items.length > 1 && (
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              style={{ color: 'var(--danger)', padding: '0.2rem' }}
                              onClick={() => removeItemRow(idx)}
                              title="Delete row"
                            >
                              ✕
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Card 4: Terms and Notes */}
          <div className="table-container" style={{ padding: '1.5rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
              4. Terms & Conditions
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Terms and Conditions</label>
                <textarea
                  className="form-control"
                  rows="3"
                  value={termsAndConditions}
                  onChange={(e) => setTermsAndConditions(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Notes / Bank Details</label>
                <textarea
                  className="form-control"
                  rows="3"
                  placeholder="Optional customer notes or payment instructions..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Authoritative Calculation Summary */}
        <div style={{ position: 'sticky', top: '1.5rem' }}>
          <div className="table-container" style={{ padding: '1.5rem', background: '#fff' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                Invoice Summary
              </h3>
              {previewLoading && (
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Calculating…</span>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                <span>Taxable Amount</span>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  {formatCurrency(taxPreview?.taxable_amount || 0)}
                </span>
              </div>

              {!isInterState ? (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                    <span>CGST</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {formatCurrency(taxPreview?.cgst_amount || 0)}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                    <span>SGST</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {formatCurrency(taxPreview?.sgst_amount || 0)}
                    </span>
                  </div>
                </>
              ) : (
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                  <span>IGST</span>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    {formatCurrency(taxPreview?.igst_amount || 0)}
                  </span>
                </div>
              )}

              {taxPreview?.round_off && taxPreview.round_off !== '0' && taxPreview.round_off !== '0.00' && (
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                  <span>Round Off</span>
                  <span style={{ fontWeight: 600 }}>{taxPreview.round_off}</span>
                </div>
              )}

              <div
                style={{
                  borderTop: '2px solid var(--border)',
                  paddingTop: '0.75rem',
                  marginTop: '0.25rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'baseline',
                }}
              >
                <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Grand Total
                </span>
                <span style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--brand)' }}>
                  {formatCurrency(taxPreview?.grand_total || 0)}
                </span>
              </div>
            </div>

            <div style={{ marginTop: '1.25rem', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Tax Engine Verified:</span> Calculations retain paise to 2 decimal places using backend Python Decimal arithmetic.
              </div>
            </div>

            <div style={{ marginTop: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={handleSubmitForApproval}
                disabled={saving || submitting}
              >
                {submitting ? 'Submitting…' : 'Submit for Approval'}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-block"
                onClick={handleSaveDraft}
                disabled={saving || submitting}
              >
                {saving ? 'Saving…' : 'Save as Draft'}
              </button>
            </div>
          </div>
        </div>
      </div>
      )}

      {/* Quick Add Customer Modal */}
      {showCustomerModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1.5rem',
          }}
          onClick={() => setShowCustomerModal(false)}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: 'var(--radius-lg)',
              width: '100%',
              maxWidth: '560px',
              padding: '1.75rem',
              boxShadow: 'var(--shadow-xl)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                Add New Customer
              </h3>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowCustomerModal(false)}
              >
                ✕
              </button>
            </div>

            {custModalError && (
              <div className="alert alert-error" style={{ marginBottom: '1rem', fontSize: '0.8125rem' }}>
                {custModalError}
              </div>
            )}

            <form onSubmit={handleCreateCustomer}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>Legal Name *</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Acme Corp India Pvt Ltd"
                    value={newCustLegalName}
                    onChange={(e) => setNewCustLegalName(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>Trade Name</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Acme Stores"
                    value={newCustTradeName}
                    onChange={(e) => setNewCustTradeName(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>GSTIN</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. 33AAAAA0000A1Z5"
                    maxLength={15}
                    value={newCustGstin}
                    onChange={(e) => setNewCustGstin(e.target.value.toUpperCase())}
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>PAN</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. AAAAA0000A"
                    maxLength={10}
                    value={newCustPan}
                    onChange={(e) => setNewCustPan(e.target.value.toUpperCase())}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>Email</label>
                  <input
                    type="email"
                    className="form-control"
                    placeholder="billing@acme.com"
                    value={newCustEmail}
                    onChange={(e) => setNewCustEmail(e.target.value)}
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>Phone</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="+91 9876543210"
                    value={newCustPhone}
                    onChange={(e) => setNewCustPhone(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label className="form-label" style={{ fontWeight: 600 }}>Billing Address Line 1</label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="Plot No. 12, Industrial Area"
                  value={newCustAddressLine1}
                  onChange={(e) => setNewCustAddressLine1(e.target.value)}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem', marginBottom: '1.25rem' }}>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>City</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Chennai"
                    value={newCustCity}
                    onChange={(e) => setNewCustCity(e.target.value)}
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>State *</label>
                  <select
                    className="form-control"
                    value={newCustStateCode}
                    onChange={(e) => setNewCustStateCode(e.target.value)}
                  >
                    {INDIAN_STATES.map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.code} - {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>Pincode</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="600001"
                    maxLength={6}
                    value={newCustPincode}
                    onChange={(e) => setNewCustPincode(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowCustomerModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Customer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
