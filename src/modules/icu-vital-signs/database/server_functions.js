/**
 * server_functions.js - Stored Procedures (MongoDB Functions)
 * Module 25: ICU Vital Signs Monitoring
 */

// 1. Compute NEWS2 Risk Band from raw score
function computeNEWS2Band(score) {
    if (score === 0) return "Low";
    if (score <= 4) return "Low-Medium";
    if (score <= 6) return "Medium";
    return "High";
}

// 2. Sample aggregation pipeline using $function for EWS alerting
function getEWSAlertPipeline(patientId) {
    return [
        { $match: { patient_id: patientId } },
        { $sort: { recorded_datetime: -1 } },
        { $limit: 10 },
        {
            $addFields: {
                band: {
                    $function: {
                        body: computeNEWS2Band.toString(),
                        args: ["$news2_score"],
                        lang: "js"
                    }
                }
            }
        }
    ];
}

module.exports = { computeNEWS2Band, getEWSAlertPipeline };
