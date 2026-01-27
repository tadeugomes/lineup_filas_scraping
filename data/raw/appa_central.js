function verificarToken(clientId) {
	
	var token = ''
	
	if(window.location.hash) {
		var hash = window.location.hash.substring(1);
		const urlParams = new URLSearchParams(hash);
		token = urlParams.get('access_token');
	} else  {
		token = localStorage.getItem(clientId) || '';
	}
	
	if (token !== undefined && token !== null && token !== '') {
		
		var decoded = jwt_decode(token);
		
		const expToken = decoded.exp;
		const timestamp = Math.floor(new Date().getTime()/1000);
		
		const cpf = decoded.upn;
		
		if ((cpf !== undefined) && (cpf !== null) && (cpf !== "") && 
			(expToken !== undefined) && (expToken !== null) && (expToken > timestamp)) {

			$('#camposLogin').html('<div class="loading"><img src="images/loading.gif" alt="Aguarde" width="120px"><h5>Aguarde...</h5><div>');
			localStorage.setItem(clientId, token);

			var authForm = document.createElement("form");
			authForm.method = "POST";
			authForm.action = "default.aspx?WCI=Default&Mv=Ok&Cert=true"; 

			var campoChave = document.createElement("input"); 
			campoChave.value = cpf;
			campoChave.name = "CHAVE";
			campoChave.type = "hidden";
			authForm.appendChild(campoChave);  

			var campoToken = document.createElement("input");  
			campoToken.value = token;
			campoToken.name = "TOKEN";
			campoToken.type = "hidden";
			authForm.appendChild(campoToken);

			document.body.appendChild(authForm);

			authForm.submit();
		}
	} else {
		localStorage.removeItem(clientId);
	}
}