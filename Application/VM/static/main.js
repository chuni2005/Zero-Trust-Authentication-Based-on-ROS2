    if (typeof ChartAnnotation !== 'undefined') {
        Chart.register(ChartAnnotation);
    } else {
        console.error("Failed to load Chartjs-plugin-annotation.js. Check file path alignment.");
    }

    let autoTriggerTimer = null; 
    document.getElementById("toggleSwitch").addEventListener("change", function() {
        const triggerBtn = document.getElementById("triggerBtn");
  
        if (this.checked) {
            triggerBtn.style.display = "none";
            sendCommand('/cmd/start');
            console.log("[Auto Loop] Automatically triggering RPi1 ROS2 packets...");
            autoTriggerTimer = setInterval(() => {
                sendCommand('/cmd/start');
                console.log("[Auto Loop] Automatically triggering RPi1 ROS2 packets...");
            }, 1000);
        } else {
            triggerBtn.style.display = "inline-block";
            if (autoTriggerTimer !== null) {
                clearInterval(autoTriggerTimer);
                autoTriggerTimer = null;
                console.log("[Auto Loop] Stopped automatic trigger.");
            }
        }
    });

    // ==========================================
    // 全域變數與指標監控
    // ==========================================
    let currentPrediction = "Waiting...";
    let currentCardColor = "#7f8c8d"; 

    let totalAttackCount = 0;     
    let detectedAttackCount = 0;  
    let wasLastSafe = true;       

    // 這 1 秒鐘監控視窗內的狀態暫存器
    let maxStatusInWindow = 0.5; // 預設為 0.5 (無資料)

    // ==========================================
    // Chart.js 圖表初始化
    // ==========================================
    const ctx = document.getElementById('securityChart').getContext('2d');

    const securityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [], 
            datasets: [{
                label: 'Security Status Matrix',
                data: [], 
                borderColor: '#7f8c8d', 
                backgroundColor: 'rgba(127, 140, 141, 0.05)',
                borderWidth: 3,
                stepped: true, 
                tension: 0,
                pointRadius: 5,
                pointBackgroundColor: [] 
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 200 },
            scales: {
                x: {
                    grid: { color: 'rgba(200, 200, 200, 0.1)' },
                    title: { display: true, text: 'Time (Real-time)', font: { weight: 'bold' } }
                },
                y: {
                    min: -0.2,
                    max: 1.2,
                    ticks: {
                        stepSize: 0.5, 
                        callback: function(value) {
                            if (value === 0) return 'Normal (0)';
                            if (value === 0.5) return 'No Data from Model (0.5)';
                            if (value === 1) return 'ATTACK! (1)';
                            return '';
                        }
                    },
                    grid: { color: 'rgba(200, 200, 200, 0.1)' }
                }
            },
            plugins: {
                legend: { display: false },
                annotation: {
                    annotations: {} 
                }
            }
        }
    });

    function updateMetricsUI() {
        document.getElementById('total-attacks').innerText = totalAttackCount;
        document.getElementById('detected-attacks').innerText = detectedAttackCount;
        if (totalAttackCount > 0) {
            const rate = Math.min(100, Math.round((detectedAttackCount / totalAttackCount) * 100));
            document.getElementById('detection-rate').innerText = rate + "%";
        } else {
            document.getElementById('detection-rate').innerText = "0%";
        }
    }

    // ==========================================
    // 高頻率狀態輪詢 (330ms) -> 收集這一秒內的所有模型推論狀態
    // ==========================================
    setInterval(() => {
        fetch('/api/get_status')
            .then(r => r.json())
            .then(data => {
                currentPrediction = data.prediction;
                currentCardColor = data.color;
                
                const val = data.status_val; // 取得後端傳來的數值 (0, 0.5, 1)

                // 核心優先權判定：
                // 如果這 330ms 抓到 1.0 (攻擊)，那這一秒的圖表必定是 1
                if (val === 1.0) {
                    maxStatusInWindow = 1.0;
                    
                    if (wasLastSafe) {
                        detectedAttackCount++;
                        updateMetricsUI();
                        wasLastSafe = false; 
                    }
                } 
                // 如果目前的暫存不是 1.0，且這次抓到的是 0.0 (正常)，則把預設的 0.5 覆蓋為 0.0
                else if (val === 0.0 && maxStatusInWindow !== 1.0) {
                    maxStatusInWindow = 0.0;
                    wasLastSafe = true;
                }
                // 如果回傳 0.5 (No Data)，且目前這 1 秒內還沒有任何正常(0)或攻擊(1)的報告，則維持 0.5

                const badgeCard = document.getElementById('status-badge-card');
                if (badgeCard) badgeCard.style.backgroundColor = currentCardColor;
                
                const predText = document.getElementById('prediction-text');
                if (predText) predText.innerText = currentPrediction;
            })
            .catch(err => console.log("[Sync Loop] Web console frontend detached from Flask backend."));
    }, 330);

    // ==========================================
    // 圖表時間軸渲染引擎 (固定 1000ms 推進一格)
    // ==========================================
    setInterval(() => {
        const maxDataPoints = 18; 
        const now = new Date();
        const timeStr = now.toTimeString().split(' ')[0];

        // 讀取過去這 1 秒間累積出來的最終最高優先權狀態
        let finalStatusValue = maxStatusInWindow;

        securityChart.data.labels.push(timeStr);
        securityChart.data.datasets[0].data.push(finalStatusValue);
        
        // 渲染顏色設定
        let pointColor = '#7f8c8d'; // 預設灰色 (No Data)
        if (finalStatusValue === 1.0) {
            pointColor = '#e74c3c'; // 紅色 (Attack)
            securityChart.data.datasets[0].borderColor = '#e74c3c';
        } else if (finalStatusValue === 0.0) {
            pointColor = '#3498db'; // 藍色 (Normal)
            securityChart.data.datasets[0].borderColor = '#3498db';
        } else {
            securityChart.data.datasets[0].borderColor = '#7f8c8d'; // 灰色折線
        }
        
        securityChart.data.datasets[0].pointBackgroundColor.push(pointColor);

        // 【關鍵：重置視窗暫存器】
        // 進入下一個 1 秒前，重新假設狀態為最底層的 0.5 (沒收到模型回應)
        maxStatusInWindow = 0.5;

        if (securityChart.data.labels.length > maxDataPoints) {
            const removedLabel = securityChart.data.labels.shift();
            securityChart.data.datasets[0].data.shift();
            securityChart.data.datasets[0].pointBackgroundColor.shift();

            const annotations = securityChart.options.plugins.annotation.annotations;
            for (const id in annotations) {
                if (annotations[id].value === removedLabel) {
                    delete annotations[id];
                }
            }
        }
        securityChart.update();
    }, 1000);

    function sendCommand(route) {
        fetch(route, {method: 'POST'});
    }

    // ==========================================
    // 模擬攻擊按鈕觸發
    // ==========================================
    function submitAttack() {
        const radios = document.getElementsByName('attackType');
        let selectedValue;

        for (const radio of radios) {
            if (radio.checked) {
                selectedValue = radio.value;
                break;
            }
        }

        totalAttackCount++;
        updateMetricsUI();

        const activeAttackLabel = document.getElementById('active-attack-type');
        activeAttackLabel.innerText = selectedValue.toUpperCase();
        activeAttackLabel.style.color = '#e74c3c';

        const toSeconds = (timeStr) => {
            const parts = timeStr.split(':');
            const d = new Date();
            d.setHours(parts[0], parts[1], parts[2], 0);
            return Math.floor(d.getTime() / 1000);
        };

        let maxTicks = 10; // 預設都是 10 秒

        if (selectedValue.toLowerCase() === 'ros2_recon') {
            maxTicks = 20;
        }

        const temp_time = new Date();
        let targetXValue = temp_time.toTimeString().split(' ')[0];
        const startXValue = temp_time.toTimeString().split(' ')[0];
        const startTimestamp = Math.floor(temp_time.getTime() / 1000);

        const zoneMinTarget = startTimestamp;
        const zoneMaxTarget = startTimestamp + maxTicks;

        const LineId = 'attack_line_' + temp_time;
        const ZoneId = 'attack_zone_' + temp_time;

        securityChart.options.plugins.annotation.annotations[LineId] = {
            type: 'line',
            scaleID: 'x',
            value: targetXValue, 
            borderColor: '#e74c3c',
            borderWidth: 2,
            borderDash: [5, 5],
            label: {
                display: true,
                content: '🎯 ' + selectedValue,
                position: 'start',
                backgroundColor: 'rgba(231, 76, 60, 0.85)',
                font: { size: 10, weight: 'bold' }
            }
        };

        securityChart.options.plugins.annotation.annotations[ZoneId] = {

            type: 'box',
            // 依照你的想法實作左邊界與右邊界：
            xMin: (ctx) => {
                const labels = ctx.chart.data.labels;
                if (labels.length === 0) return startXValue;

                const minTimeStr = labels[0];

                const minTimestamp = toSeconds(minTimeStr);

                if (zoneMinTarget < minTimestamp) {
                    return minTimeStr;
                } else {
                    return startXValue;
                }
            },
            xMax: (ctx) => {
                const labels = ctx.chart.data.labels;
                if (labels.length === 0) return startXValue;

                const nowTimeStr = labels[labels.length - 1];
                const minTimeStr = labels[0];
                const nowTimestamp = toSeconds(nowTimeStr);
                const minTimestamp = toSeconds(minTimeStr);

                if (zoneMaxTarget > nowTimestamp) {
                    return nowTimeStr;
                } else if (zoneMaxTarget < minTimestamp){
                    return minTimeStr;
                } else {
                    const maxDate = new Date(zoneMaxTarget * 1000);
                    return maxDate.toTimeString().split(' ')[0];
                }
            },
            backgroundColor: 'rgba(231, 76, 60, 0.15)',
            borderWidth: 0,
            label: {
                display: true,
                position: 'start',
                color: '#e74c3c',
                font: { size: 10, weight: 'bold' }
            }
        };
        
        securityChart.update();
        fetch('/cmd/attack', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: selectedValue })
        });
    }