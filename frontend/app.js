
const apigClient = apigClientFactory.newClient({});

// ================================
// SEARCH PHOTOS
// ================================

window.searchPhotos = async function () {

    console.log("Search button clicked!");

    const query = document.getElementById("searchQuery").value.trim();
    const resultsDiv = document.getElementById("searchResults");

    if (!query) {
        alert("Please enter a search query");
        return;
    }

    resultsDiv.innerHTML = "Searching...";

    try {

        const params = {
            q: query
        };

        const response = await apigClient.searchGet(
            params,
            {},
            {}
        );

        console.log("Search API response:", response);

        const results = response.data.results || [];

        displayPhotos(results);

    } catch (error) {

    console.error("Search error:", error);

    if (error.response) {
        console.log("HTTP Status:", error.response.status);
        console.log("Response body:", error.response.data);
        console.log("Response headers:", error.response.headers);
    }

    resultsDiv.innerHTML = "Search failed. Check console.";
}
};


// ================================
// DISPLAY PHOTOS
// ================================

function displayPhotos(results) {

    const resultsDiv = document.getElementById("searchResults");

    resultsDiv.innerHTML = "";

    if (!results || results.length === 0) {
        resultsDiv.innerHTML = "<p>No photos found.</p>";
        return;
    }

    results.forEach(photo => {

        const card = document.createElement("div");
        card.className = "photo-card";

        const img = document.createElement("img");
        img.src = photo.url;
        img.alt = "Search result photo";

        const labels = document.createElement("p");
        labels.textContent = (photo.labels || []).join(", ");

        card.appendChild(img);
        card.appendChild(labels);

        resultsDiv.appendChild(card);

    });

}


// ================================
// UPLOAD PHOTOS
// ================================


window.uploadPhoto = async function () {
    const file = document.getElementById("photoFile").files[0];

    console.log("FILE DEBUG:", {
        name: file.name,
        type: file.type,
        size: file.size
    });
    const customLabels =
        document.getElementById("customLabels").value.trim();
    const uploadStatus = document.getElementById("uploadStatus");

    if (!file) {
        alert("Please select a photo.");
        return;
    }

    uploadStatus.innerHTML = "Uploading...";

    try {
        // Generate a unique S3 object key
        const objectKey = `${Date.now()}-${file.name}`;

        const params = {
            object: objectKey
        };

        const additionalParams = {
            headers: {
                "Content-Type": file.type,
                "x-amz-meta-customlabels": customLabels
            }
        };

        const response = await apigClient.uploadPut(
            params,
            file,
            additionalParams
        );

        console.log("Upload response:", response);
        uploadStatus.innerHTML = "Photo uploaded successfully!";

    } catch (error) {
        console.error("Upload error:", error);
        console.error("Response body:", error.response?.data);
        uploadStatus.innerHTML = "Upload failed. Check console.";
    }
};
