require('dotenv').config({ path: '/fluxsign/.env' }); // Load environment variables

const zeltrezjs = require('zeltrezjs');
const btcmessage = require('bitcoinjs-message');

const privKey = process.env.PRIVATE_KEY;

if (!privKey) {
    console.error("? Error: PRIVATE_KEY is not set in .env");
    process.exit(1);
}


async function signMessage(message) {

    const privateKeyHex = privKey.length === 64 ? privKey : zeltrezjs.address.WIFToPrivKey(privKey);
    const pk = Buffer.from(privateKeyHex, 'hex');
    const mysignature = btcmessage.sign(message, pk, true);

    return mysignature.toString('base64');
}

const args = process.argv.slice(2);
const message = args[0];

if (!message) {
    console.error("? Error: No message provided for signing.");
    process.exit(1);
}

signMessage(message).then(signature => {
    console.log(signature);
}).catch(err => {
    console.error("? Error:", err);
    process.exit(1);
});
