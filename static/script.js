function refreshPage() {
    location.reload();
}

function closeApp() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.close_window(); 
    } else {
      alert('PyWebView API is not available.');
    }
}

async function exitKiosk() {
    try {
        await fetch('/exit_kiosk');  // calls Flask route
        alert('Kiosk mode exited (browser closed).');
    } catch (error) {
        console.error(error);
        alert('Could not exit kiosk mode.');
    }
}

$(document).ready(function () {
    // jQuery selectors for widgets
    const $speedElement = $("#speed");
    const $paceElement = $("#pace");
    const $bpmElement = $("#bpm");    
    const $energyElement = $("#energy");
    const $tableBody = $("#averageSpeeds");
    const $totalDistanceElement = $("#total-distance");
    const $runningTimeElement = $("#running-time");
    const speedChartCtx = $("#speedChart")[0].getContext("2d");

   
    // Chart data
    let chartData = {
        labels: [], // Time labels in seconds
        datasets: [
            {
                label: "Speed (km/h)",
                data: [], // Speed data
                borderColor: "blue",
                borderWidth: 2,
                fill: false,
            },
            {
                label: "Average Speed (km/h)",
                data: [], // Average speed data
                borderColor: "red",
                borderWidth: 2,
                borderDash: [5, 5], // Dashed line
                fill: false,
            }
        ]
    };

    // Initialize Chart.js instance
    const speedChart = new Chart(speedChartCtx, {
        type: "line",
        data: chartData,
        options: {
            responsive: true,
            scales: {
                x: {
                    title: { display: true, text: "Time (s)" }
                },
                y: {
                    min: 0, // Minimum speed
                    max: 20, // Maximum speed
                    title: { display: true, text: "Speed (km/h)" }
                }
            }
        }
    });


    // Helper function to format time
    function formatTime(seconds, showHours = true) {
        const hours = String(Math.floor(seconds / 3600)).padStart(2, '0');
        const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
        const secs = String(seconds % 60).padStart(2, '0');
        if (showHours) return `${hours}:${minutes}:${secs}`;
        else return `${minutes}:${secs}`;
    }

    // Function to fetch data from Flask API
    function fetchTreadmillData() {
        $.get("/api/treadmill_data", function(data) {
            console.log(data);
            console.log("Data received from server");

            // Update widgets using jQuery
            var speed = data.speed.toFixed(1);
            var bpm = data.bpm;
            var limits = data.limits;
            $speedElement.text(`${speed}`);
            $paceElement.text(data.pace);
            $bpmElement.text(data.bpm);
            $energyElement.text(data.energy);
            $totalDistanceElement.text(`${data.distance.toFixed(2)} km`);
            $runningTimeElement.text(formatTime(data.running_time));

            // Example: Using the values in your script
            $('#limits').html(
                    `<p>Speed Yellow: ${limits.speed_yellow}</p>
                     <p>Speed Red: ${limits.speed_red}</p>
                     <p>BPM Yellow: ${limits.bpm_yellow}</p>
                     <p>BPM Red: ${limits.bpm_red}</p>`
            );

            // Change widget color based on speed
            if (speed < limits.speed_yellow) $("#widget_pace").attr("class", "widget bg-success text-white rounded p-4");
            else if (speed < limits.speed_red) $("#widget_pace").attr("class", "widget bg-warning text-dark rounded p-4");
            else $("#widget_pace").attr("class", "widget bg-danger text-white rounded p-4");

            // Change widget color based on bpm
            if (bpm < limits.bpm_yellow) $("#widget_bpm").attr("class", "col-8 col-sm-6 bg-success text-white");
            else if (bpm < limits.bpm_red) $("#widget_bpm").attr("class", "col-8 col-sm-6 bg-warning text-dark");
            else $("#widget_bpm").attr("class", "col-8 col-sm-6 bg-danger text-white");

            // Update table dynamically
            $tableBody.empty();  // Clear the table body first
            $.each(data.average_speeds, function(index, entry) {
                lap_time = formatTime(entry[0], false);
                $tableBody.append(`
                    <tr class="h1">
                        <td>${index + 1}</td>                    
                        <td>${lap_time}</td>
                        <td>${entry[1].toFixed(0)}</td>                        
                        <td>${entry[2].toFixed(1)}</td>
                        <td>${entry[3]}</td>
                        <td>${entry[4].toFixed(0)}</td
                    </tr>
                `);
            });

            // Add speed data to the chart
            chartData.labels.push(data.running_time); // Use elapsed time for labels
            chartData.datasets[0].data.push(speed); // Push speed to the dataset

            // Calculate and update average speed
            const totalSpeed = chartData.datasets[0].data.reduce((sum, value) => sum + parseFloat(value), 0);
            const averageSpeed = (totalSpeed / chartData.datasets[0].data.length).toFixed(1);
            chartData.datasets[1].data = Array(chartData.labels.length).fill(averageSpeed); // Red line for avg speed

            // Limit data points to maintain a clean chart
            if (chartData.labels.length > 60) {
                chartData.labels.shift();
                chartData.datasets[0].data.shift();
            }

            // Update the chart
            speedChart.update();
        }).fail(function() {
            console.error("Failed to fetch treadmill data.");
        });
    }

    // Fetch data every second
    setInterval(fetchTreadmillData, 1000);
});
