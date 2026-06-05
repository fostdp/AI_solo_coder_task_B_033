const ChartModule = {
    trendChart: null,
    alarmTypeChart: null,

    createTrendChart(canvasId, data, deviceType) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        if (this.trendChart) {
            this.trendChart.destroy();
        }

        const labels = data.map(d => {
            const dt = new Date(d.timestamp);
            return `${dt.getHours().toString().padStart(2, '0')}:${dt.getMinutes().toString().padStart(2, '0')}`;
        });

        let datasets = [];

        if (deviceType === 'env_sensor') {
            datasets = [
                {
                    label: '温度 (℃)',
                    data: data.map(d => d.temperature),
                    borderColor: '#ff6b6b',
                    backgroundColor: 'rgba(255, 107, 107, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: '湿度 (%)',
                    data: data.map(d => d.humidity),
                    borderColor: '#4ecdc4',
                    backgroundColor: 'rgba(78, 205, 196, 0.1)',
                    yAxisID: 'y2',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: '氧气 (%)',
                    data: data.map(d => d.oxygen),
                    borderColor: '#00d4ff',
                    backgroundColor: 'rgba(0, 212, 255, 0.1)',
                    yAxisID: 'y3',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: '甲烷 (%)',
                    data: data.map(d => d.methane),
                    borderColor: '#ffaa00',
                    backgroundColor: 'rgba(255, 170, 0, 0.1)',
                    yAxisID: 'y4',
                    tension: 0.3,
                    fill: true,
                    hidden: true
                },
                {
                    label: '硫化氢 (ppm)',
                    data: data.map(d => d.hydrogen_sulfide),
                    borderColor: '#a855f7',
                    backgroundColor: 'rgba(168, 85, 247, 0.1)',
                    yAxisID: 'y5',
                    tension: 0.3,
                    fill: true,
                    hidden: true
                }
            ];
        } else if (deviceType === 'fan') {
            datasets = [
                {
                    label: '转速 (%)',
                    data: data.map(d => d.speed || 0),
                    borderColor: '#00ff88',
                    backgroundColor: 'rgba(0, 255, 136, 0.1)',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: '电流 (A)',
                    data: data.map(d => d.current || 0),
                    borderColor: '#ffaa00',
                    backgroundColor: 'rgba(255, 170, 0, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.3,
                    fill: true
                }
            ];
        } else if (deviceType === 'pump') {
            datasets = [
                {
                    label: '液位 (m)',
                    data: data.map(d => d.level || 0),
                    borderColor: '#00d4ff',
                    backgroundColor: 'rgba(0, 212, 255, 0.1)',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: '流量 (m³/h)',
                    data: data.map(d => d.flow_rate || 0),
                    borderColor: '#00ff88',
                    backgroundColor: 'rgba(0, 255, 136, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.3,
                    fill: true,
                    hidden: true
                }
            ];
        }

        const options = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#a0aec0',
                        font: { size: 10 },
                        boxWidth: 12
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 28, 50, 0.95)',
                    titleColor: '#00d4ff',
                    bodyColor: '#e0e6ed',
                    borderColor: 'rgba(0, 212, 255, 0.3)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(107, 122, 144, 0.2)'
                    },
                    ticks: {
                        color: '#6b7a90',
                        font: { size: 9 },
                        maxTicksLimit: 8
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(107, 122, 144, 0.2)'
                    },
                    ticks: {
                        color: '#6b7a90',
                        font: { size: 9 }
                    }
                }
            }
        };

        if (deviceType === 'env_sensor') {
            options.scales.y1 = {
                position: 'right',
                display: false,
                grid: { drawOnChartArea: false }
            };
            options.scales.y2 = {
                position: 'right',
                display: false,
                grid: { drawOnChartArea: false }
            };
            options.scales.y3 = {
                position: 'right',
                display: false,
                grid: { drawOnChartArea: false }
            };
            options.scales.y4 = {
                position: 'right',
                display: false,
                grid: { drawOnChartArea: false }
            };
            options.scales.y5 = {
                position: 'right',
                display: false,
                grid: { drawOnChartArea: false }
            };
        } else if (deviceType === 'fan' || deviceType === 'pump') {
            options.scales.y1 = {
                position: 'right',
                display: false,
                grid: { drawOnChartArea: false }
            };
        }

        this.trendChart = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options
        });

        return this.trendChart;
    },

    createAlarmTypeChart(alarmTypeData) {
        const ctx = document.getElementById('alarmTypeChart');
        if (!ctx) return;

        if (this.alarmTypeChart) {
            this.alarmTypeChart.destroy();
        }

        const labels = Object.keys(alarmTypeData).map(key => CONFIG.ALARM_NAMES[key] || key);
        const data = Object.values(alarmTypeData);
        const colors = ['#ff4444', '#ff6b00', '#ffaa00', '#8b5cf6', '#00d4ff', '#00ff88'];

        this.alarmTypeChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{
                    data,
                    backgroundColor: colors.slice(0, data.length),
                    borderColor: 'rgba(15, 28, 50, 0.8)',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 28, 50, 0.95)',
                        titleColor: '#00d4ff',
                        bodyColor: '#e0e6ed',
                        borderColor: 'rgba(0, 212, 255, 0.3)',
                        borderWidth: 1
                    }
                }
            }
        });

        return this.alarmTypeChart;
    },

    destroyCharts() {
        if (this.trendChart) {
            this.trendChart.destroy();
            this.trendChart = null;
        }
        if (this.alarmTypeChart) {
            this.alarmTypeChart.destroy();
            this.alarmTypeChart = null;
        }
    }
};
