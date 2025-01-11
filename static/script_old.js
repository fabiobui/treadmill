$(document).ready(function () {

    // jQuery selectors for widgets
    const $speedElement = $("#speed");
    const $paceElement = $("#pace");
    const $tableBody = $("#averageSpeeds");
    const $totalDistanceElement = $("#total-distance");
    const $runningTimeElement = $("#running-time");
    const speedChartCtx = $("#speedChart")[0].getContext("2d");
    
    // Chart data
    let chartData = {
        labels: [],
        datasets: [
            {
                label: "Instant Pace (min/km)",
                data: [],
                yAxisID: 'y1',
                borderColor: "blue",
                borderWidth: 2,
                fill: false
            },
            {
                label: "Average Speed (km markers)",
                type: "bar",
                data: [],
                yAxisID: 'y2',
                backgroundColor: []
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
                y1: {
                    position: 'left',
                    title: { display: true, text: "Pace (min/km)" },
                    ticks: { reverse: true }  // Faster pace at the top
                },
                y2: {
                    position: 'right',
                    title: { display: true, text: "Average Speed (km/h)" }
                }
            }
        }
    });
    
    // Helper function to format time
    function formatTime(seconds) {
        const hours = String(Math.floor(seconds / 3600)).padStart(2, '0');
        const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
        const secs = String(seconds % 60).padStart(2, '0');
        return `${hours}:${minutes}:${secs}`;
    }
    
    // Handle Server-Sent Events (SSE)
    const eventSource = new EventSource("/data_stream_json");
    let prevSpeed = 0;  // Keep track of the previous average speed for bar coloring
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        console.log(data);
        console.log("Data received from server");
        alert("Data received from server");

        // Update widgets using jQuery
        $speedElement.text(`${data.speed} km/h`);
        $paceElement.text(data.pace);
        $totalDistanceElement.text(`${data.distance.toFixed(2)} km`);
        $runningTimeElement.text(formatTime(data.running_time));
    
        // Update table dynamically
        $tableBody.empty();  // Clear the table body first
        $.each(data.average_speeds, function(index, entry) {
            $tableBody.append(`
                <tr>
                    <td>${index + 1}</td>
                    <td>${entry[0].toFixed(2)} km/h</td>
                    <td>${entry[1]}</td>
                </tr>
            `);
        });
    
        // Update chart dynamically
        chartData.labels.push(data.distance.toFixed(2));
        chartData.datasets[0].data.push(parseFloat(data.pace.replace(":", ".")));
    
        // Add a bar at every kilometer marker with dynamic color
        if (data.average_speeds.length > chartData.datasets[1].data.length) {
            const currentSpeed = data.average_speeds[data.average_speeds.length - 1][0];
            chartData.datasets[1].data.push(currentSpeed);
        
            // Add color based on comparison with previous speed
            const barColor = currentSpeed > prevSpeed ? "green" : "red";
            chartData.datasets[1].backgroundColor.push(barColor);
        
            prevSpeed = currentSpeed;
        }
    
        // Update the chart
        speedChart.update();
    };
    
    // Error handling for SSE
    eventSource.onerror = function() {
        console.error("Error occurred with EventSource. Retrying...");
    };

});
