const express = require('express');
const cors = require('cors');
const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

// Supabase Connection
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

app.get('/', (req, res) => {
    res.send("SevaSpot Backend is Running Perfectly (Validity Based System)!");
});

// प्लॅन व्हॅलिडिटी चेक करण्याची API
app.post('/check-validity', async (req, res) => {
    const { userId } = req.body;

    if (!userId) {
        return res.status(400).json({ error: "User ID आवश्यक आहे." });
    }

    try {
        // युजरचे प्रोफाईल फेच करा
        const { data: userProfile, error: profileError } = await supabase
            .from('user_profiles')
            .select('plan_status, expire_date')
            .eq('id', userId)
            .single();

        if (profileError || !userProfile) {
            return res.status(400).json({ error: "युजरची माहिती मिळाली नाही." });
        }

        const today = new Date();
        const expiryDate = new Date(userProfile.expire_date);

        // प्लॅनची मुदत संपली आहे का ते तपासा
        if (userProfile.plan_status !== 'Active' || today > expiryDate) {
            // जर मुदत संपली असेल तर डेटाबेसमध्ये स्टेटस 'Expired' करा
            await supabase
                .from('user_profiles')
                .update({ plan_status: 'Expired' })
                .eq('id', userId);

            return res.status(403).json({ 
                success: false, 
                error: "तुमचा प्लॅन संपला आहे. कृपया रिचार्ज करा.",
                is_active: false
            });
        }

        // प्लॅन चालू असल्यास
        res.json({ 
            success: true, 
            message: "प्लॅन ॲक्टिव्ह आहे.", 
            is_active: true,
            expire_date: userProfile.expire_date
        });

    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Admin API: प्लॅन रिचार्ज मंजूर करणे
app.post('/approve-recharge', async (req, res) => {
    const { requestId, userId, planDays } = req.body;

    // TODO: Admin verification should be done here

    try {
        // १. रिक्वेस्टचे स्टेटस 'Approved' करा
        await supabase
            .from('recharge_requests')
            .update({ status: 'Approved' })
            .eq('id', requestId);

        // २. युजरचे प्रोफाईल अपडेट करा (Validity वाढवा)
        const newExpiryDate = new Date();
        newExpiryDate.setDate(newExpiryDate.getDate() + parseInt(planDays));

        await supabase
            .from('user_profiles')
            .update({ 
                plan_status: 'Active', 
                expire_date: newExpiryDate.toISOString().split('T')[0] // YYYY-MM-DD format
            })
            .eq('id', userId);

        res.json({ success: true, message: "प्लॅन यशस्वीरीत्या ॲक्टिव्हेट झाला!" });

    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});


const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
